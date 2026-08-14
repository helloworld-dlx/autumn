"""Phase 3B-2: Pi-side file pull client for Runner POST /v1/file.

Reuses Bridge's HMAC-SHA256 signer primitives and the same runner HMAC key.
Does NOT introduce a new endpoint, a new key, or a new signature scheme —
Runner reconstructs the canonical envelope from request headers + body path
(see _file_signed_payload in jarvis_runner/network.py).

Public API:
    build_file_export_envelope(path, config, key) -> dict
    pull_file(path, config, *, transfer_root=...) -> (result_dict | None, error_dict | None)
    cleanup_transfer(transfer_id, transfer_root=...) -> bool
    MAX_FILE_SIZE
    TRANSFER_ID_PATTERN
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import socket
import stat
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit

from .auth import load_secret
from .config import BridgeConfig

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16777216 bytes — must match Runner's limit
CHUNK_SIZE = 64 * 1024

# Header names must mirror jarvis_runner/network.py:FILE_AUTH_HEADERS exactly.
FILE_AUTH_HEADERS = {
    "request_id": "X-Autumn-Request-Id",
    "issued_at":  "X-Autumn-Issued-At",
    "expires_at": "X-Autumn-Expires-At",
    "nonce":      "X-Autumn-Nonce",
    "key_id":     "X-Autumn-Key-Id",
    "signature":  "X-Autumn-Signature",
}

# Runner regex: ^[A-Za-z0-9_-]{1,100}$. We mirror it for cleanup-id validation.
TRANSFER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def _canonical_payload(r: dict) -> bytes:
    """Identical shape to runner_client.canonical_payload.
    Signs everything except the signature field itself.
    """
    return json.dumps(
        {k: v for k, v in r.items() if k != "signature"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def build_file_export_envelope(path: str, c: BridgeConfig, key: bytes) -> dict:
    """Build the signed envelope dict that Runner reconstructs on its side.
    Mirrors jarvis_runner/network.py:_file_signed_payload exactly.
    """
    now = datetime.now(timezone.utc)
    env = {
        "protocol_version": "1.0",
        "request_id": str(uuid.uuid4()),
        "target_device": c.runner_target_device,
        "action": "file.export",
        "arguments": {"path": path},
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=60)).isoformat(),
        "nonce": secrets.token_urlsafe(24),
        "key_id": c.runner_key_id,
    }
    env["signature"] = hmac.new(key, _canonical_payload(env), hashlib.sha256).hexdigest()
    return env


def _path_basename(path: str) -> str:
    """Windows + POSIX last component. Used only for diagnostic metadata;
    never used to construct a Pi save path."""
    if not path:
        return ""
    # ntpath handles both \\ and / separators
    import ntpath
    base = ntpath.basename(path.replace("/", "\\"))
    return base or ""


def _safe_remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _safe_rmdir(dirpath: Path) -> None:
    try:
        dirpath.rmdir()
    except OSError:
        pass


def _fail_transfer(transfer_dir: Path, transfer_id: str, code: str, **extra) -> dict:
    """Common failure path: remove .part, remove empty transfer dir, return error JSON."""
    _safe_remove(transfer_dir / "data.bin.part")
    _safe_rmdir(transfer_dir)
    err = {"status": "failed", "error_code": code, "transfer_id": transfer_id}
    err.update(extra)
    return err


def pull_file(path: str, c: BridgeConfig, *, transfer_root: Path) -> tuple:
    """End-to-end secure pull of a Windows file to Pi.

    Returns:
        (success_dict | None, error_dict | None). Exactly one is non-None.

    success_dict:
        {"status": "succeeded", "transfer_id", "local_path",
         "filename", "size", "sha256"}

    error_dict:
        {"status": "failed", "error_code", "transfer_id", ...}
    """
    transfer_root = Path(transfer_root).resolve()
    transfer_root.mkdir(parents=True, exist_ok=True)
    try:
        transfer_root.chmod(0o700)
    except OSError:
        pass

    transfer_id = secrets.token_urlsafe(24)
    transfer_dir = transfer_root / transfer_id
    transfer_dir.mkdir(parents=True, exist_ok=False)
    try:
        transfer_dir.chmod(0o700)
    except OSError:
        pass

    part_path = transfer_dir / "data.bin.part"
    final_path = transfer_dir / "data.bin"
    meta_path = transfer_dir / "meta.json"

    # ------- Build signed envelope -------
    try:
        key = load_secret(c.runner_key_path)
    except ValueError:
        return None, _fail_transfer(transfer_dir, transfer_id, "BRIDGE_KEY_UNAVAILABLE")

    env = build_file_export_envelope(path, c, key)
    headers = {
        "Content-Type": "application/json",
        FILE_AUTH_HEADERS["request_id"]: env["request_id"],
        FILE_AUTH_HEADERS["issued_at"]: env["issued_at"],
        FILE_AUTH_HEADERS["expires_at"]: env["expires_at"],
        FILE_AUTH_HEADERS["nonce"]: env["nonce"],
        FILE_AUTH_HEADERS["key_id"]: env["key_id"],
        FILE_AUTH_HEADERS["signature"]: env["signature"],
    }
    body = json.dumps({"path": path}).encode()

    # ------- Open HTTP connection (streaming) -------
    parts = urlsplit(c.runner_base_url)
    host = parts.hostname
    port = parts.port or 27891
    conn = None
    try:
        conn = http.client.HTTPConnection(host, port, timeout=c.request_timeout_seconds)
        conn.request("POST", "/v1/file", body, headers)
        resp = conn.getresponse()
    except (TimeoutError, socket.timeout):
        if conn is not None:
            try: conn.close()
            except Exception: pass
        return None, _fail_transfer(transfer_dir, transfer_id, "RUNNER_TIMEOUT")
    except (ConnectionRefusedError, ConnectionResetError, OSError):
        if conn is not None:
            try: conn.close()
            except Exception: pass
        return None, _fail_transfer(transfer_dir, transfer_id, "RUNNER_OFFLINE")

    # ------- Read response (status + headers + streaming body) -------
    try:
        status = resp.status

        if status != 200:
            err_body = resp.read()
            try:
                err = json.loads(err_body) if err_body else {}
                err_code = err.get("error_code", "RUNNER_ERROR")
            except Exception:
                err_code = "RUNNER_ERROR"
            try: conn.close()
            except Exception: pass
            return None, _fail_transfer(transfer_dir, transfer_id, err_code,
                                       http_status=status)

        # 200: must have Content-Length
        cl_header = resp.getheader("Content-Length")
        if not cl_header or not cl_header.isdecimal():
            try: resp.read()
            except Exception: pass
            try: conn.close()
            except Exception: pass
            return None, _fail_transfer(transfer_dir, transfer_id,
                                       "RUNNER_NO_CONTENT_LENGTH")

        declared_size = int(cl_header)
        if declared_size > MAX_FILE_SIZE:
            try: resp.read()
            except Exception: pass
            try: conn.close()
            except Exception: pass
            return None, _fail_transfer(transfer_dir, transfer_id,
                                       "FILE_TOO_LARGE",
                                       declared_size=declared_size,
                                       max_file_size=MAX_FILE_SIZE)

        # Filename header is metadata only.
        filename_header = resp.getheader("X-Autumn-Filename") or ""
        # size_header = resp.getheader("X-Autumn-Size")  # not enforced

        # ------- Streaming write to .part -------
        sha256 = hashlib.sha256()
        received = 0
        truncated = False
        try:
            with open(part_path, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_FILE_SIZE:
                        truncated = True
                        break
                    sha256.update(chunk)
                    f.write(chunk)
        except OSError:
            try: conn.close()
            except Exception: pass
            return None, _fail_transfer(transfer_dir, transfer_id, "WRITE_FAILED")

        try: conn.close()
        except Exception: pass

        if truncated:
            return None, _fail_transfer(transfer_dir, transfer_id,
                                       "FILE_TOO_LARGE_STREAMED",
                                       received=received,
                                       max_file_size=MAX_FILE_SIZE)

        if received != declared_size:
            return None, _fail_transfer(transfer_dir, transfer_id,
                                       "SIZE_MISMATCH",
                                       received=received,
                                       declared_size=declared_size)

        # ------- Atomic rename + perms -------
        os.replace(part_path, final_path)
        try:
            os.chmod(final_path, 0o600)
        except OSError:
            pass

        # ------- meta.json -------
        metadata = {
            "transfer_id": transfer_id,
            "filename": filename_header,
            "size": received,
            "sha256": sha256.hexdigest(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state": "completed",
        }
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        try:
            os.chmod(meta_path, 0o600)
        except OSError:
            pass

        return {
            "status": "succeeded",
            "transfer_id": transfer_id,
            "local_path": str(final_path),
            "filename": filename_header or _path_basename(path),
            "size": received,
            "sha256": metadata["sha256"],
        }, None
    except (TimeoutError, socket.timeout):
        return None, _fail_transfer(transfer_dir, transfer_id, "RUNNER_TIMEOUT")
    except (ConnectionRefusedError, ConnectionResetError, OSError):
        return None, _fail_transfer(transfer_dir, transfer_id, "RUNNER_OFFLINE")


def cleanup_transfer(transfer_id: str, transfer_root: Path) -> tuple:
    """Remove a transfer dir. Strict path validation — no traversal, no symlinks out.

    Returns:
        (ok: bool, error_dict | None)
    """
    if not isinstance(transfer_id, str) or not TRANSFER_ID_PATTERN.fullmatch(transfer_id):
        return False, {"status": "failed", "error_code": "INVALID_TRANSFER_ID"}
    transfer_root = Path(transfer_root).resolve()
    target = (transfer_root / transfer_id).resolve()
    # Must be under transfer_root
    try:
        target.relative_to(transfer_root)
    except ValueError:
        return False, {"status": "failed", "error_code": "INVALID_TRANSFER_ID"}
    if not target.exists():
        return False, {"status": "failed", "error_code": "NOT_FOUND"}
    if target.is_symlink():
        return False, {"status": "failed", "error_code": "INVALID_TRANSFER_ID"}
    if not target.is_dir():
        return False, {"status": "failed", "error_code": "NOT_A_DIRECTORY"}

    # Refuse to delete anything outside the dir or with symlinks pointing out
    for child in target.rglob("*"):
        try:
            st = child.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            return False, {"status": "failed", "error_code": "INVALID_TRANSFER_ID"}

    import shutil
    try:
        shutil.rmtree(target)
    except OSError as e:
        return False, {"status": "failed", "error_code": "REMOVE_FAILED",
                       "detail": str(e)}
    return True, None
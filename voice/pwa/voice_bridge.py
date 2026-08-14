#!/usr/bin/env python3
"""Minimal utterance Voice Bridge for Autumn.  It has no persistent state."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import threading
import tempfile
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, urlopen

HOST = os.environ.get("VOICE_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("VOICE_BRIDGE_PORT", "18791"))
ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
GATEWAY_HELPER = ROOT / "gateway_turn.mjs"
MAX_AUDIO_BYTES = 20 * 1024 * 1024
AUDIO_TTL_SECONDS = 600
AUDIOS: dict[str, tuple[Path, float]] = {}
PHONE_TOUCH_URL = "http://127.0.0.1:27901/v1/internal/nodes/xiaomi15/touch"


class BridgeError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def assert_loopback(host: str) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("VOICE_BRIDGE_HOST must be loopback")


def touch_phone_presence(opener=None) -> bool:
    request = Request(PHONE_TOUCH_URL, data=b"", method="POST")
    try:
        open_request = opener or build_opener(ProxyHandler({})).open
        with open_request(request, timeout=1) as response:
            return response.status == 200
    except (OSError, HTTPError, URLError, TimeoutError):
        return False


MAIN_CONVERSATION_ID = "main"


def conversation_key(conversation_id: str | None) -> str:
    """Map a stable Companion conversation identity to its Gateway key."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", conversation_id or "")[:80]
    return f"companion:{safe or MAIN_CONVERSATION_ID}"


class GatewayTurnClient:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()

    def _start(self) -> subprocess.Popen[str]:
        if self.process and self.process.poll() is None:
            return self.process
        self.process = subprocess.Popen(
            ["/usr/bin/node", str(GATEWAY_HELPER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
        )
        return self.process

    def start(self) -> None:
        with self.lock:
            self._start()

    def turn(self, transcript: str, voice_key: str) -> str:
        with self.lock:
            process = self._start()
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Gateway helper pipes unavailable")
            process.stdin.write(json.dumps({"message": transcript, "sessionKey": voice_key}, ensure_ascii=False) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                self.process = None
                raise RuntimeError("Gateway helper stopped")
        result = json.loads(line)
        if not result.get("ok") or not isinstance(result.get("text"), str) or not result["text"].strip():
            raise RuntimeError(str(result.get("error") or "Gateway returned no reply"))
        return result["text"].strip()


GATEWAY = GatewayTurnClient()


def autumn_turn(transcript: str, voice_key: str, gateway: GatewayTurnClient = GATEWAY) -> str:
    try:
        return gateway.turn(transcript, voice_key)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise BridgeError("GATEWAY_FAILED", "Autumn Gateway turn failed", 502) from exc


def multipart_body(audio: bytes, filename: str, content_type: str) -> tuple[bytes, str]:
    boundary = f"----AutumnVoice{uuid.uuid4().hex}"
    preamble = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"
                "FunAudioLLM/SenseVoiceSmall\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n").encode()
    return preamble + audio + f"\r\n--{boundary}--\r\n".encode(), boundary


def siliconflow_transcribe(audio: bytes, filename: str, content_type: str) -> str:
    key = os.environ.get("SILICONFLOW_API_KEY")
    if not key:
        raise BridgeError("NEEDS_API_KEY", "SILICONFLOW_API_KEY is not configured", 503)
    body, boundary = multipart_body(audio, filename, content_type)
    request = Request("https://api.siliconflow.cn/v1/audio/transcriptions", data=body, method="POST",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BridgeError("SILICONFLOW_FAILED", "Speech transcription failed") from exc
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise BridgeError("SILICONFLOW_EMPTY", "Speech transcription was empty")
    return text.strip()


def minimax_tts(text: str) -> Path:
    MEDIA.mkdir(mode=0o700, exist_ok=True)
    output = MEDIA / f"{uuid.uuid4().hex}.mp3"
    # This is the existing bundled MiniMax TTS helper path previously smoke-tested
    # on this Pi.  It is not a new SDK client or a shell command.
    helper = """import fs from 'node:fs';
const [output, text] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync('/home/xyzlh/.openclaw/openclaw.json', 'utf8'));
const auth = await import('file:///home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/provider-auth-L08Tydtg.js');
const tts = await import('file:///home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/tts-CNLIRC78.js');
const apiKey = await auth.s({ cfg, provider: 'minimax' });
if (!apiKey) throw new Error('MINIMAX_AUTH_UNAVAILABLE');
const audio = await tts.i({ text, apiKey, baseUrl: 'https://api.minimaxi.com', model: 'speech-2.8-turbo', voiceId: 'Chinese (Mandarin)_Warm_Girl', format: 'mp3', sampleRate: 32000, timeoutMs: 45000 });
if (!Buffer.isBuffer(audio) || audio.length < 128) throw new Error('TTS_AUDIO_INVALID');
fs.writeFileSync(output, audio, { mode: 0o600 });
"""
    try:
        result = subprocess.run(["/usr/bin/node", "--input-type=module", "-", str(output), text], input=helper,
                                capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise BridgeError("MINIMAX_TTS_FAILED", "MiniMax speech synthesis timed out") from exc
    if result.returncode:
        raise BridgeError("MINIMAX_TTS_FAILED", "MiniMax speech synthesis failed")
    if not output.is_file() or output.stat().st_size == 0:
        raise BridgeError("MINIMAX_TTS_FAILED", "MiniMax returned no audio")
    return output


def cleanup_audio() -> None:
    cutoff = time.monotonic() - AUDIO_TTL_SECONDS
    for token, (path, created) in list(AUDIOS.items()):
        if created < cutoff:
            path.unlink(missing_ok=True)
            AUDIOS.pop(token, None)


def process_turn(audio: bytes, filename: str, mime: str, requested_conversation: str | None,
                 stt=siliconflow_transcribe, autumn=autumn_turn, tts=minimax_tts) -> dict[str, object]:
    if not audio:
        raise BridgeError("AUDIO_REQUIRED", "Upload one audio utterance", 400)
    if len(audio) > MAX_AUDIO_BYTES:
        raise BridgeError("AUDIO_TOO_LARGE", "Audio exceeds 20 MiB", 413)
    started = time.monotonic()
    transcript = stt(audio, filename, mime)  # Must succeed before Autumn is invoked.
    stt_ms = round((time.monotonic() - started) * 1000)
    key = conversation_key(requested_conversation)
    reply = autumn(transcript, key)
    autumn_ms = round((time.monotonic() - started) * 1000) - stt_ms
    path = tts(reply)
    total_ms = round((time.monotonic() - started) * 1000)
    token = uuid.uuid4().hex
    AUDIOS[token] = (path, time.monotonic())
    cleanup_audio()
    return {"conversationKey": key, "transcript": transcript, "reply": reply, "audioUrl": f"/api/audio/{token}",
            "latencyMs": {"stt": stt_ms, "autumn": autumn_ms, "tts": total_ms - stt_ms - autumn_ms, "total": total_ms}}


def parse_multipart(content_type: str, body: bytes) -> tuple[bytes, str, str, str | None]:
    match = re.search(r"boundary=([^;]+)", content_type)
    if not match:
        raise BridgeError("INVALID_UPLOAD", "multipart boundary required", 400)
    boundary = b"--" + match.group(1).strip('"').encode()
    fields: dict[str, tuple[dict[str, str], bytes]] = {}
    for part in body.split(boundary)[1:]:
        if part.startswith(b"--"):
            break
        head, separator, data = part.strip(b"\r\n").partition(b"\r\n\r\n")
        if not separator:
            continue
        headers = {line.split(b":", 1)[0].decode().lower(): line.split(b":", 1)[1].decode().strip()
                   for line in head.split(b"\r\n") if b":" in line}
        disposition = headers.get("content-disposition", "")
        name = re.search(r'name="([^"]+)"', disposition)
        if name:
            fields[name.group(1)] = (headers, data)
    if "audio" not in fields:
        raise BridgeError("AUDIO_REQUIRED", "Field named audio is required", 400)
    headers, audio = fields["audio"]
    disposition = headers.get("content-disposition", "")
    file_name = (re.search(r'filename="([^"]*)"', disposition) or ["audio.webm"])[1]
    mime = headers.get("content-type", mimetypes.guess_type(file_name)[0] or "application/octet-stream")
    conversation = fields.get("conversationId", ({}, b""))[1].decode("utf-8", "ignore") or None
    return audio, file_name, mime, conversation


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass  # Do not log transcript, paths, headers, or credentials.

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"ok": True, "listen": "loopback"})
            return
        if self.path == "/" or self.path == "/index.html":
            data = (ROOT / "index.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/continuous_voice.mjs":
            data = (ROOT / "continuous_voice.mjs").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/sw.js":
            data = (ROOT / "sw.js").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        static = {"/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"), "/favicon.ico": ("icons/autumn-192.png", "image/png"), "/icons/autumn-192.png": ("icons/autumn-192.png", "image/png"), "/icons/autumn-512.png": ("icons/autumn-512.png", "image/png")}
        if self.path in static:
            name, content_type = static[self.path]; data = (ROOT / name).read_bytes()
            self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path.startswith("/api/audio/"):
            item = AUDIOS.get(self.path.rsplit("/", 1)[-1])
            if not item or not item[0].is_file(): self.send_error(404); return
            data = item[0].read_bytes()
            self.send_response(200); self.send_header("Content-Type", "audio/mpeg"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data); return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/presence/touch":
            touch_phone_presence()
            self.send_json(200, {"ok": True})
            return
        if self.path != "/api/turn": self.send_error(404); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_AUDIO_BYTES + 65536: raise BridgeError("AUDIO_TOO_LARGE", "Audio exceeds 20 MiB", 413)
            audio, name, mime, requested = parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
            result = process_turn(audio, name, mime, requested)
            touch_phone_presence()  # Non-critical telemetry; failure must not affect the turn.
            self.send_json(200, result)
        except BridgeError as exc:
            self.send_json(exc.status, {"error": exc.code, "message": exc.message})
        except Exception:
            self.send_json(500, {"error": "INTERNAL_ERROR", "message": "Voice Bridge failed"})


if __name__ == "__main__":
    assert_loopback(HOST)
    MEDIA.mkdir(mode=0o700, exist_ok=True)
    GATEWAY.start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

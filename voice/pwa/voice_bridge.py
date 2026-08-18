#!/usr/bin/env python3
"""Minimal Companion/Voice Bridge for Autumn.

Only small attachment display metadata is persisted outside the repository so a
chat attachment card can survive reload when the deployed Gateway history API
omits attachment metadata. File contents and transcripts are never copied.
"""
from __future__ import annotations

import base64
import inspect
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
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, urlopen

HOST = os.environ.get("VOICE_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("VOICE_BRIDGE_PORT", "18791"))
ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
GATEWAY_HELPER = ROOT / "gateway_turn.mjs"
TTS_STREAM_HELPER = ROOT / "minimax_tts_stream.mjs"
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_BARGE_INTENT_BYTES = 2 * 1024 * 1024
MAX_CHAT_BYTES = 16 * 1024  # text only
MAX_CHAT_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_CHAT_ATTACHMENT_TOTAL_BYTES = 12 * 1024 * 1024
MAX_CHAT_ATTACHMENTS = 3
MAX_CHAT_REQUEST_BYTES = 17 * 1024 * 1024
MAX_HISTORY_MESSAGES = 40
AUDIO_TTL_SECONDS = 600
AUDIO_STREAM_TTL_SECONDS = 180
AUDIOS: dict[str, tuple[Path, float]] = {}
AUDIO_STREAMS: dict[str, "AudioStream"] = {}
AUDIO_STREAMS_LOCK = threading.Lock()
PHONE_TOUCH_URL = "http://127.0.0.1:27901/v1/internal/nodes/xiaomi15/touch"
COMPANION_STATUS_URL = "http://127.0.0.1:27901/v1/internal/companion/status"
TRANSFER_ROOT = Path(os.environ.get("AUTUMN_TRANSFER_ROOT", "/home/xyzlh/jarvis-bridge/transfers"))
TRANSFER_ID = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
ATTACHMENT_META_PATH = Path(os.environ.get(
    "AUTUMN_COMPANION_ATTACHMENT_META_PATH",
    str(Path.home() / ".openclaw" / "autumn-companion-attachments-v1.json"),
))
ATTACHMENT_META_LOCK = threading.Lock()
MAX_ATTACHMENT_META_RECORDS = 500
HIDDEN_FILES_PATH = Path(os.environ.get(
    "AUTUMN_COMPANION_HIDDEN_FILES_PATH",
    str(Path.home() / ".openclaw" / "autumn-companion-hidden-files-v1.json"),
))
HIDDEN_FILES_LOCK = threading.Lock()
MAX_HIDDEN_FILE_RECORDS = 500
CONVERSATION_TITLES_PATH = Path(os.environ.get(
    "AUTUMN_COMPANION_TITLES_PATH",
    str(Path.home() / ".openclaw" / "autumn-companion-titles-v1.json"),
))
CONVERSATION_TITLES_LOCK = threading.Lock()
MAX_CONVERSATION_TITLE_RECORDS = 500
MAX_CONVERSATION_TITLE_CHARS = 30
CONVERSATION_UI_STATE_PATH = Path(os.environ.get(
    "AUTUMN_COMPANION_UI_STATE_PATH",
    str(Path.home() / ".openclaw" / "conversation_ui_state.json"),
))
CONVERSATION_UI_STATE_LOCK = threading.Lock()
MAX_ARCHIVED_CONVERSATIONS = 500
VISION_CAST_TTL_SECONDS = 10 * 60
VISION_CAST_MAX_EVENTS = 120
VISION_CASTS: dict[str, dict[str, object]] = {}
VISION_CASTS_LOCK = threading.Lock()
PRESENCE_DEVICE_RE = re.compile(r"(?:电脑|Windows|设备)", re.IGNORECASE)
PRESENCE_STATUS_RE = re.compile(r"(?:在线|离线|在不在线|是否连接|连着|连接)", re.IGNORECASE)


class AudioStream:
    """Small in-memory fan-out for one progressive MP3 response.

    MiniMax produces bytes in a background process. The browser can attach
    after the first bytes are ready and receives already-buffered bytes followed
    by live bytes. Streams are one-shot and bounded by a short TTL.
    """

    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.chunks: list[bytes] = []
        self.created = time.monotonic()
        self.first_chunk_at: float | None = None
        self.done = False
        self.error: str | None = None
        self.cancelled = False
        self.process: subprocess.Popen[bytes] | None = None
        self.byte_count = 0

    def attach_process(self, process: subprocess.Popen[bytes]) -> None:
        with self.condition:
            self.process = process
            if self.cancelled and process.poll() is None:
                process.terminate()

    def push(self, chunk: bytes) -> bool:
        if not chunk:
            return True
        with self.condition:
            if self.cancelled:
                return False
            if self.first_chunk_at is None:
                self.first_chunk_at = time.monotonic()
            self.chunks.append(bytes(chunk))
            self.byte_count += len(chunk)
            self.condition.notify_all()
            return True

    def finish(self) -> None:
        with self.condition:
            self.done = True
            self.condition.notify_all()

    def fail(self, message: str) -> None:
        with self.condition:
            self.error = message or "MiniMax streaming TTS failed"
            self.done = True
            self.condition.notify_all()

    def wait_first(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.first_chunk_at is None and not self.done and not self.error and not self.cancelled:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            return self.first_chunk_at is not None

    def iter_chunks(self):
        index = 0
        while True:
            with self.condition:
                while index >= len(self.chunks) and not self.done and not self.error and not self.cancelled:
                    self.condition.wait(1.0)
                if index < len(self.chunks):
                    chunk = self.chunks[index]
                    index += 1
                elif self.done or self.error or self.cancelled:
                    return
                else:
                    continue
            yield chunk

    def cancel(self) -> None:
        with self.condition:
            self.cancelled = True
            process = self.process
            self.condition.notify_all()
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass


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


def _prune_vision_casts(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    stale = [
        cast_id for cast_id, item in VISION_CASTS.items()
        if now - float(item.get("updated", item.get("created", now))) > VISION_CAST_TTL_SECONDS
    ]
    for cast_id in stale:
        VISION_CASTS.pop(cast_id, None)


def create_vision_cast(label: str) -> dict[str, object]:
    clean = re.sub(r"\s+", " ", str(label or "")).strip()[:60] or "Phone Camera"
    cast_id = "vc_" + uuid.uuid4().hex[:18]
    now = time.monotonic()
    with VISION_CASTS_LOCK:
        _prune_vision_casts(now)
        VISION_CASTS[cast_id] = {
            "id": cast_id,
            "label": clean,
            "created": now,
            "updated": now,
            "seq": 0,
            "events": [],
        }
    return {"id": cast_id, "label": clean}


def list_vision_casts() -> list[dict[str, object]]:
    now = time.monotonic()
    with VISION_CASTS_LOCK:
        _prune_vision_casts(now)
        return [
            {
                "id": cast_id,
                "label": str(item.get("label") or "Phone Camera"),
                "ageMs": max(0, int((now - float(item.get("created", now))) * 1000)),
            }
            for cast_id, item in VISION_CASTS.items()
        ]


def push_vision_signal(cast_id: str, role: str, signal_type: str, payload: object) -> int:
    if role not in {"sender", "viewer"}:
        raise BridgeError("VISION_SIGNAL_INVALID", "Invalid vision signal role", 400)
    if signal_type not in {"offer", "answer", "ice", "hello"}:
        raise BridgeError("VISION_SIGNAL_INVALID", "Invalid vision signal type", 400)
    if len(json.dumps(payload, ensure_ascii=False)) > 32_000:
        raise BridgeError("VISION_SIGNAL_TOO_LARGE", "Vision signal is too large", 413)
    now = time.monotonic()
    with VISION_CASTS_LOCK:
        _prune_vision_casts(now)
        item = VISION_CASTS.get(cast_id)
        if item is None:
            raise BridgeError("VISION_CAST_NOT_FOUND", "Remote camera is no longer available", 404)
        seq = int(item.get("seq", 0)) + 1
        item["seq"] = seq
        item["updated"] = now
        events = item.setdefault("events", [])
        assert isinstance(events, list)
        events.append({"seq": seq, "role": role, "type": signal_type, "payload": payload})
        if len(events) > VISION_CAST_MAX_EVENTS:
            del events[:-VISION_CAST_MAX_EVENTS]
        return seq


def poll_vision_signals(cast_id: str, target_role: str, after: int) -> dict[str, object]:
    if target_role not in {"sender", "viewer"}:
        raise BridgeError("VISION_SIGNAL_INVALID", "Invalid vision signal target", 400)
    now = time.monotonic()
    with VISION_CASTS_LOCK:
        _prune_vision_casts(now)
        item = VISION_CASTS.get(cast_id)
        if item is None:
            raise BridgeError("VISION_CAST_NOT_FOUND", "Remote camera is no longer available", 404)
        item["updated"] = now
        events = item.get("events")
        if not isinstance(events, list):
            events = []
        visible = [
            event for event in events
            if isinstance(event, dict)
            and int(event.get("seq", 0)) > after
            and event.get("role") != target_role
        ]
        return {"events": visible, "latestSeq": int(item.get("seq", 0))}


def close_vision_cast(cast_id: str) -> bool:
    with VISION_CASTS_LOCK:
        return VISION_CASTS.pop(cast_id, None) is not None


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

    def turn(self, message: str, voice_key: str, source: str = "voice", attachments: list[dict[str, object]] | None = None,
             on_trace=None) -> str:
        with self.lock:
            process = self._start()
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Gateway helper pipes unavailable")
            request = {"message": message, "sessionKey": voice_key, "source": source}
            if source == "chat" and attachments:
                request["attachments"] = attachments
            process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                self.process = None
                raise RuntimeError("Gateway helper stopped")
        result = json.loads(line)
        if on_trace is not None and isinstance(result.get("toolTrace"), list):
            for trace in result["toolTrace"]:
                if isinstance(trace, dict):
                    on_trace(trace)
        if not result.get("ok") or not isinstance(result.get("text"), str) or not result["text"].strip():
            raise RuntimeError(str(result.get("error") or "Gateway returned no reply"))
        return result["text"].strip()

    def turn_stream(self, message: str, voice_key: str, on_delta, source: str = "voice", on_trace=None) -> str:
        request_id = uuid.uuid4().hex
        callback_error: Exception | None = None
        with self.lock:
            process = self._start()
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Gateway helper pipes unavailable")
            process.stdin.write(json.dumps({
                "message": message,
                "sessionKey": voice_key,
                "source": source,
                "stream": True,
                "requestId": request_id,
            }, ensure_ascii=False) + "\n")
            process.stdin.flush()
            while True:
                line = process.stdout.readline()
                if not line:
                    self.process = None
                    raise RuntimeError("Gateway helper stopped")
                event = json.loads(line)
                if event.get("requestId") not in {None, request_id}:
                    continue
                if event.get("type") == "delta":
                    if callback_error is None:
                        try:
                            on_delta(str(event.get("delta") or ""), str(event.get("text") or ""))
                        except Exception as exc:  # Drain this serialized Gateway turn before surfacing the callback failure.
                            callback_error = exc
                    continue
                if event.get("type") == "final" or event.get("type") is None:
                    result = event
                    break
        if callback_error is not None:
            raise callback_error
        if on_trace is not None:
            traces = result.get("toolTrace")
            if isinstance(traces, list):
                for trace in traces:
                    if isinstance(trace, dict):
                        on_trace(trace)
        if not result.get("ok") or not isinstance(result.get("text"), str) or not result["text"].strip():
            raise RuntimeError(str(result.get("error") or "Gateway returned no reply"))
        return result["text"].strip()

    def history(self, voice_key: str) -> list[dict[str, str]]:
        with self.lock:
            process = self._start()
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Gateway helper pipes unavailable")
            process.stdin.write(json.dumps({"action": "history", "sessionKey": voice_key}) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                self.process = None
                raise RuntimeError("Gateway helper stopped")
        result = json.loads(line)
        messages = result.get("messages")
        if not result.get("ok") or not isinstance(messages, list):
            raise RuntimeError(str(result.get("error") or "Gateway history unavailable"))
        return messages

    def sessions(self) -> list[dict[str, object]]:
        with self.lock:
            process = self._start()
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Gateway helper pipes unavailable")
            process.stdin.write(json.dumps({"action": "sessions", "sessionKey": conversation_key(MAIN_CONVERSATION_ID)}) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                self.process = None
                raise RuntimeError("Gateway helper stopped")
        result = json.loads(line)
        sessions = result.get("sessions")
        if not result.get("ok") or not isinstance(sessions, list):
            raise RuntimeError(str(result.get("error") or "Gateway sessions unavailable"))
        return sessions


    def effective_tools(self, conversation_id: str = MAIN_CONVERSATION_ID) -> list[str]:
        key = conversation_key(conversation_id)
        with self.lock:
            process = self._start()
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Gateway helper pipes unavailable")
            process.stdin.write(json.dumps({"action": "effective_tools", "sessionKey": key}) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                self.process = None
                raise RuntimeError("Gateway helper stopped")
        result = json.loads(line)
        tools = result.get("tools")
        if not result.get("ok") or not isinstance(tools, list):
            raise RuntimeError(str(result.get("code") or result.get("error") or "Gateway effective tools unavailable"))
        return [str(name) for name in tools if isinstance(name, str)]

GATEWAY = GatewayTurnClient()


def autumn_turn(transcript: str, voice_key: str, gateway: GatewayTurnClient = GATEWAY, source: str = "voice",
                attachments: list[dict[str, object]] | None = None, on_trace=None) -> str:
    try:
        if on_trace is None:
            return gateway.turn(transcript, voice_key, source, attachments)
        return gateway.turn(transcript, voice_key, source, attachments, on_trace)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise BridgeError("GATEWAY_FAILED", "Autumn Gateway turn failed", 502) from exc


def autumn_turn_stream(transcript: str, voice_key: str, on_delta, gateway: GatewayTurnClient = GATEWAY,
                       on_trace=None) -> str:
    try:
        return gateway.turn_stream(transcript, voice_key, on_delta, "voice", on_trace)
    except BridgeError:
        raise
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise BridgeError("GATEWAY_FAILED", "Autumn Gateway streaming turn failed", 502) from exc


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


def register_audio(path: Path) -> str:
    token = uuid.uuid4().hex
    AUDIOS[token] = (path, time.monotonic())
    cleanup_audio()
    return f"/api/audio/{token}"


def _run_minimax_tts_stream(text: str, stream: AudioStream) -> None:
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            ["/usr/bin/node", str(TTS_STREAM_HELPER), text],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0,
        )
        stream.attach_process(process)
        if process.stdout is None:
            raise RuntimeError("MiniMax TTS stream stdout unavailable")
        while True:
            chunk = os.read(process.stdout.fileno(), 8192)
            if not chunk:
                break
            if not stream.push(chunk):
                break
        if stream.cancelled:
            if process.poll() is None:
                process.terminate()
            stream.finish()
            return
        stderr = b""
        if process.stderr is not None:
            stderr = process.stderr.read(4096) or b""
        returncode = process.wait(timeout=5)
        if returncode != 0:
            detail = stderr.decode("utf-8", "replace").strip().splitlines()[-1:]
            raise RuntimeError(detail[0] if detail else "MiniMax streaming TTS helper failed")
        if stream.byte_count < 128:
            raise RuntimeError("MiniMax streaming TTS returned no audio")
        stream.finish()
    except Exception as exc:
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        stream.fail(str(exc))


def cleanup_audio_streams() -> None:
    cutoff = time.monotonic() - AUDIO_STREAM_TTL_SECONDS
    stale: list[tuple[str, AudioStream]] = []
    with AUDIO_STREAMS_LOCK:
        for token, stream in list(AUDIO_STREAMS.items()):
            if stream.created < cutoff:
                stale.append((token, stream))
                AUDIO_STREAMS.pop(token, None)
    for _token, stream in stale:
        stream.cancel()


def minimax_tts_stream(text: str, first_byte_timeout: float = 8.0) -> str:
    if not isinstance(text, str) or not text.strip():
        raise BridgeError("MINIMAX_TTS_FAILED", "MiniMax speech synthesis text was empty")
    if not TTS_STREAM_HELPER.is_file():
        raise BridgeError("MINIMAX_TTS_FAILED", "MiniMax streaming TTS helper is unavailable")
    stream = AudioStream()
    token = uuid.uuid4().hex
    with AUDIO_STREAMS_LOCK:
        AUDIO_STREAMS[token] = stream
    cleanup_audio_streams()
    threading.Thread(target=_run_minimax_tts_stream, args=(text, stream), daemon=True).start()
    if not stream.wait_first(first_byte_timeout):
        with AUDIO_STREAMS_LOCK:
            AUDIO_STREAMS.pop(token, None)
        stream.cancel()
        raise BridgeError("MINIMAX_TTS_STREAM_FAILED", stream.error or "MiniMax streaming TTS produced no first audio")
    return f"/api/audio-stream/{token}"


def first_speakable_prefix(text: str) -> tuple[str, int] | None:
    """Return one natural early TTS prefix and the exact consumed character count.

    3C-1 intentionally synthesizes at most one early prefix before the final
    reply. This cuts first-voice latency without creating a large TTS queue yet.
    """
    if not isinstance(text, str) or not text:
        return None
    leading = len(text) - len(text.lstrip())
    body = text[leading:]
    if len(body) < 6:
        return None
    for match in re.finditer(r'[。！？!?][”’"\']?', body):
        end = match.end()
        if end >= 6:
            return body[:end].strip(), leading + end
    if len(body) >= 20:
        window = body[:36]
        soft = max((window.rfind(mark) for mark in ("，", ",", "；", ";", "：", ":")), default=-1)
        if soft >= 12:
            end = soft + 1
            return body[:end].strip(), leading + end
    if len(body) >= 36:
        return body[:36].strip(), leading + 36
    return None


def is_presence_query(text: str) -> bool:
    return bool(PRESENCE_DEVICE_RE.search(text or "") and PRESENCE_STATUS_RE.search(text or ""))


def supports_on_trace(callback) -> bool:
    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD or parameter.name == "on_trace" for parameter in parameters)


def presence_status_from_trace(traces: list[dict[str, object]]) -> str | None:
    for trace in traces:
        if trace.get("tool") != "autumn_nodes" or trace.get("phase") != "result" or trace.get("error"):
            continue
        result = trace.get("result")
        if isinstance(result, dict) and result.get("node") == "windows-main" and result.get("status") in {"ONLINE", "OFFLINE"}:
            return str(result["status"])
    return None


def fail_closed_presence_reply(query: str, reply: str, traces: list[dict[str, object]]) -> str:
    if not is_presence_query(query):
        return reply
    status = presence_status_from_trace(traces)
    if status is None:
        return "我现在没能可靠确认电脑状态。"
    says_online = bool(re.search(r"在线|连着|已连接", reply))
    says_offline = bool(re.search(r"离线|不在线|未连接", reply))
    if (status == "ONLINE" and says_offline) or (status == "OFFLINE" and says_online) or (not says_online and not says_offline):
        return "我现在没能可靠确认电脑状态。"
    return reply


STATUS_UI_TOOLS = {
    "autumn_nodes", "jarvis_ping", "jarvis_system_info", "jarvis_system_status",
    "worker_control_status", "worker_submit", "worker_result",
}
FILES_UI_TOOLS = {
    "jarvis_search_files", "jarvis_list_directory", "autumn_file_return",
    "autumn_companion_artifact",
}


def ui_hints_from_activity(traces: list[dict[str, object]],
                           reply_attachments: list[dict[str, object]] | None = None) -> list[str]:
    """Map real tool lifecycle evidence to a small stable spatial presentation hint set."""
    hints: list[str] = []
    for trace in traces:
        if not isinstance(trace, dict) or trace.get("phase") not in {"start", "result"}:
            continue
        tool = trace.get("tool")
        if tool in FILES_UI_TOOLS and "files" not in hints:
            hints.append("files")
        elif tool in STATUS_UI_TOOLS and "status" not in hints:
            hints.append("status")
    if reply_attachments and "files" not in hints:
        hints.append("files")
    return hints[:3]


BARGE_WAKE_RE = re.compile(r"(?:\bautumn\b|秋(?:天)?[，,、\s]*)", re.IGNORECASE)
BARGE_STRONG_RE = re.compile(
    r"(?:等等|等一下|等会(?:儿)?|停一下|先停|先别说|别说了|打断一下|"
    r"换个问题|换一个问题|换个话题|换一个话题|换题|"
    r"\bwait\b|\bhold on\b|\bstop\b|\bpause\b|"
    r"\bchange (?:the )?(?:topic|question)\b|\bnew question\b)",
    re.IGNORECASE,
)


def barge_intent_from_transcript(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return False
    # "不对" alone is deliberately not enough; it is common background speech.
    return bool(BARGE_WAKE_RE.search(normalized) or BARGE_STRONG_RE.search(normalized))


def process_barge_intent(audio: bytes, filename: str, mime: str, stt=siliconflow_transcribe) -> dict[str, object]:
    if not audio:
        raise BridgeError("AUDIO_REQUIRED", "Upload one interruption candidate", 400)
    if len(audio) > MAX_BARGE_INTENT_BYTES:
        raise BridgeError("BARGE_INTENT_TOO_LARGE", "Interruption candidate exceeds 2 MiB", 413)
    transcript = stt(audio, filename, mime)
    return {"interrupt": barge_intent_from_transcript(transcript), "transcript": transcript}


def cleanup_audio() -> None:
    cutoff = time.monotonic() - AUDIO_TTL_SECONDS
    for token, (path, created) in list(AUDIOS.items()):
        if created < cutoff:
            path.unlink(missing_ok=True)
            AUDIOS.pop(token, None)
    cleanup_audio_streams()


def _auto_conversation_title(text: str) -> str:
    """Create a compact deterministic title from the first user turn.

    This intentionally avoids an extra model call during 3B. It follows the
    first-turn title lifecycle used by projects such as LibreChat, but uses a
    local normalizer so naming is free, fast, and cannot create another session.
    """
    original = re.sub(r"\s+", " ", str(text or "")).strip()
    original = re.sub(r"^[#>*\-–—•·\s]+", "", original).strip()
    if not original:
        return "新对话"

    title = original
    prefixes = (
        r"^(?:请你?|麻烦你?|劳驾你?)\s*(?:帮我|帮忙)?\s*",
        r"^(?:你能不能|能不能|可以不可以|可不可以|可以|能否)\s*(?:帮我|帮忙)?\s*",
        r"^(?:我想要?|我希望|我需要)\s*(?:继续)?\s*",
        r"^(?:帮我|帮忙|给我)\s*",
        r"^(?:please\s+|could\s+you\s+|can\s+you\s+|would\s+you\s+|help\s+me\s+|i\s+(?:want|need|would\s+like)\s+to\s+)",
    )
    for _ in range(3):
        previous = title
        for pattern in prefixes:
            title = re.sub(pattern, "", title, count=1, flags=re.IGNORECASE).strip()
        if title == previous:
            break

    actions = (
        r"^(?:继续)?(?:学习|了解|研究|讲解|解释|看看|看一下|规划一下|规划|整理一下|整理|复习一下|复习|讨论一下|讨论|聊聊)\s*",
        r"^(?:learn|understand|explain|plan|review|discuss)\s+",
    )
    for pattern in actions:
        updated = re.sub(pattern, "", title, count=1, flags=re.IGNORECASE).strip()
        if updated != title:
            title = updated
            break

    title = re.split(r"[。！？!?\n\r]", title, maxsplit=1)[0].strip(" \t，,；;：:。.!！?？")
    if not title:
        title = re.split(r"[。！？!?\n\r]", original, maxsplit=1)[0].strip(" \t，,；;：:。.!！?？")
    if not title:
        return "新对话"
    if len(title) > MAX_CONVERSATION_TITLE_CHARS:
        title = title[:MAX_CONVERSATION_TITLE_CHARS].rstrip() + "…"
    return title


def _read_conversation_titles(path: Path = CONVERSATION_TITLES_PATH) -> dict[str, dict[str, object]]:
    if not path.exists() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("titles"), dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, item in payload["titles"].items():
        if not isinstance(key, str) or not key.startswith("companion:") or not isinstance(item, dict):
            continue
        title = item.get("title")
        stored_at = item.get("storedAt")
        if isinstance(title, str) and title.strip() and isinstance(stored_at, int):
            out[key] = {"title": title[:MAX_CONVERSATION_TITLE_CHARS + 1], "storedAt": stored_at}
    return out


def _write_conversation_titles(titles: dict[str, dict[str, object]], path: Path = CONVERSATION_TITLES_PATH) -> None:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise OSError("conversation titles path must not be a symlink")
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, prefix=path.name + ".", delete=False) as handle:
            temp_name = handle.name
            json.dump({"version": 1, "titles": titles}, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def ensure_conversation_title(conversation_key_value: str, first_user_text: str,
                              path: Path = CONVERSATION_TITLES_PATH) -> bool:
    if conversation_key_value == conversation_key(MAIN_CONVERSATION_ID):
        return False
    title = _auto_conversation_title(first_user_text)
    if title == "新对话":
        return False
    with CONVERSATION_TITLES_LOCK:
        titles = _read_conversation_titles(path)
        if conversation_key_value in titles:
            return False
        titles[conversation_key_value] = {"title": title, "storedAt": int(time.time())}
        if len(titles) > MAX_CONVERSATION_TITLE_RECORDS:
            ordered = sorted(titles.items(), key=lambda item: item[1].get("storedAt", 0))
            for old_key, _item in ordered[:len(titles) - MAX_CONVERSATION_TITLE_RECORDS]:
                titles.pop(old_key, None)
        _write_conversation_titles(titles, path)
    return True


def load_conversation_title(conversation_id: str, path: Path = CONVERSATION_TITLES_PATH) -> str:
    key = conversation_key(conversation_id)
    with CONVERSATION_TITLES_LOCK:
        item = _read_conversation_titles(path).get(key)
    if not isinstance(item, dict):
        return ""
    value = item.get("title")
    return value.strip() if isinstance(value, str) else ""


def _read_conversation_ui_state(path: Path = CONVERSATION_UI_STATE_PATH) -> dict[str, dict[str, object]]:
    if not path.exists() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("archived"), dict):
        return {}
    archived: dict[str, dict[str, object]] = {}
    for conversation_id, item in payload["archived"].items():
        if not isinstance(conversation_id, str) or conversation_id == MAIN_CONVERSATION_ID or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", conversation_id) or not isinstance(item, dict):
            continue
        archived_at, title = item.get("archivedAt"), item.get("title")
        if isinstance(archived_at, int):
            archived[conversation_id] = {"archivedAt": archived_at, "title": str(title or "")[:MAX_CONVERSATION_TITLE_CHARS + 1]}
    return archived


def _write_conversation_ui_state(archived: dict[str, dict[str, object]], path: Path = CONVERSATION_UI_STATE_PATH) -> None:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise OSError("conversation UI state path must not be a symlink")
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, prefix=path.name + ".", delete=False) as handle:
            temp_name = handle.name
            json.dump({"archived": archived}, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush(); os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def process_archive_conversation(conversation_id: str, title: object = "", path: Path = CONVERSATION_UI_STATE_PATH) -> dict[str, object]:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", conversation_id or "")[:80]
    if not safe or safe != conversation_id:
        raise BridgeError("CONVERSATION_INVALID", "Conversation id is invalid", 400)
    if safe == MAIN_CONVERSATION_ID:
        raise BridgeError("MAIN_CONVERSATION_PROTECTED", "Main cannot be archived", 409)
    with CONVERSATION_UI_STATE_LOCK:
        archived = _read_conversation_ui_state(path)
        archived[safe] = {"archivedAt": int(time.time()), "title": str(title or "")[:MAX_CONVERSATION_TITLE_CHARS + 1]}
        if len(archived) > MAX_ARCHIVED_CONVERSATIONS:
            oldest = min(archived, key=lambda key: int(archived[key].get("archivedAt", 0)))
            archived.pop(oldest, None)
        _write_conversation_ui_state(archived, path)
    return {"ok": True, "archived": safe}


def process_restore_conversation(conversation_id: str, path: Path = CONVERSATION_UI_STATE_PATH) -> dict[str, object]:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", conversation_id or "")[:80]
    if not safe or safe != conversation_id:
        raise BridgeError("CONVERSATION_INVALID", "Conversation id is invalid", 400)
    if safe == MAIN_CONVERSATION_ID:
        raise BridgeError("MAIN_CONVERSATION_PROTECTED", "Main cannot be restored", 409)
    with CONVERSATION_UI_STATE_LOCK:
        archived = _read_conversation_ui_state(path)
        archived.pop(safe, None)
        _write_conversation_ui_state(archived, path)
    return {"ok": True, "restored": safe}


def process_turn(audio: bytes, filename: str, mime: str, requested_conversation: str | None,
                 stt=siliconflow_transcribe, autumn=autumn_turn, tts=minimax_tts,
                 title_path: Path = CONVERSATION_TITLES_PATH, new_conversation: bool = False,
                 history=GATEWAY.history, metadata_path: Path = ATTACHMENT_META_PATH,
                 transfer_root: Path = TRANSFER_ROOT) -> dict[str, object]:
    if not audio:
        raise BridgeError("AUDIO_REQUIRED", "Upload one audio utterance", 400)
    if len(audio) > MAX_AUDIO_BYTES:
        raise BridgeError("AUDIO_TOO_LARGE", "Audio exceeds 20 MiB", 413)
    started = time.monotonic()
    transcript = stt(audio, filename, mime)
    stt_ms = round((time.monotonic() - started) * 1000)
    key = conversation_key(requested_conversation)
    before_transfers = _returned_transfer_ids(transfer_root)
    tool_trace: list[dict[str, object]] = []
    if supports_on_trace(autumn):
        reply = autumn(transcript, key, on_trace=tool_trace.append)
    else:
        reply = autumn(transcript, key)
    reply = fail_closed_presence_reply(transcript, reply, tool_trace)
    reply_attachments = _new_returned_attachments(before_transfers, transfer_root)
    if _should_create_first_turn_title(requested_conversation, new_conversation, title_path):
        try:
            ensure_conversation_title(key, transcript, title_path)
        except (OSError, json.JSONDecodeError):
            pass
    if reply_attachments:
        try:
            rows = history(key)
            assistant_id = _latest_assistant_message_id(rows)
            if assistant_id:
                store_attachment_metadata(key, assistant_id, reply_attachments, metadata_path)
        except (OSError, RuntimeError, json.JSONDecodeError):
            pass
    autumn_ms = round((time.monotonic() - started) * 1000) - stt_ms
    path = tts(reply)
    total_ms = round((time.monotonic() - started) * 1000)
    audio_url = register_audio(path)
    return {
        "conversationKey": key,
        "transcript": transcript,
        "reply": reply,
        "replyAttachments": _safe_attachment_metadata(reply_attachments),
        "audioUrl": audio_url,
        "toolTrace": tool_trace,
        "uiHints": ui_hints_from_activity(tool_trace, reply_attachments),
        "latencyMs": {"stt": stt_ms, "autumn": autumn_ms, "tts": total_ms - stt_ms - autumn_ms, "total": total_ms},
    }



def process_turn_stream(audio: bytes, filename: str, mime: str, requested_conversation: str | None, emit,
                        stt=siliconflow_transcribe, autumn_stream=autumn_turn_stream, tts=minimax_tts,
                        tts_stream=minimax_tts_stream,
                        title_path: Path = CONVERSATION_TITLES_PATH, new_conversation: bool = False,
                        history=GATEWAY.history, metadata_path: Path = ATTACHMENT_META_PATH,
                        transfer_root: Path = TRANSFER_ROOT) -> dict[str, object]:
    if not audio:
        raise BridgeError("AUDIO_REQUIRED", "Upload one audio utterance", 400)
    if len(audio) > MAX_AUDIO_BYTES:
        raise BridgeError("AUDIO_TOO_LARGE", "Audio exceeds 20 MiB", 413)

    started = time.monotonic()
    transcript = stt(audio, filename, mime)
    stt_done = time.monotonic()
    stt_ms = round((stt_done - started) * 1000)
    key = conversation_key(requested_conversation)
    emit({"type": "meta", "conversationKey": key, "transcript": transcript, "latencyMs": {"stt": stt_ms}})

    before_transfers = _returned_transfer_ids(transfer_root)
    streamed = ""
    first_text_ms: int | None = None
    first_voice_ms: int | None = None
    audio_seq = 0
    tool_trace: list[dict[str, object]] = []
    presence_query = is_presence_query(transcript)

    def on_delta(delta: str, accumulated: str) -> None:
        nonlocal streamed, first_text_ms
        streamed = accumulated or (streamed + delta)
        if first_text_ms is None and streamed.strip():
            first_text_ms = round((time.monotonic() - stt_done) * 1000)
        if streamed and not presence_query:
            emit({"type": "text", "text": streamed, "latencyMs": {"firstText": first_text_ms}})

    emitted_ui_hints: set[str] = set()

    def on_trace(trace: dict[str, object]) -> None:
        tool_trace.append(trace)
        for hint in ui_hints_from_activity([trace]):
            if hint in emitted_ui_hints:
                continue
            emitted_ui_hints.add(hint)
            emit({"type": "ui", "present": [hint]})

    if supports_on_trace(autumn_stream):
        reply = autumn_stream(transcript, key, on_delta, on_trace=on_trace)
    else:
        reply = autumn_stream(transcript, key, on_delta)
    final_observed = time.monotonic()

    reply = fail_closed_presence_reply(transcript, reply, tool_trace)
    if presence_query:
        if reply.strip():
            first_text_ms = first_text_ms or round((time.monotonic() - stt_done) * 1000)
            emit({"type": "text", "text": reply, "latencyMs": {"firstText": first_text_ms}})

    # 3C-2 stability rule: synthesize exactly one final reply per turn.
    #
    # Earlier 3C-2 builds combined an early partial-TTS request with a second
    # final/remainder TTS request. On real Xiaomi playback that path could repeat
    # speech when provider/browser streaming boundaries did not line up exactly.
    # Keep text deltas for responsiveness, but use the proven V0.2 full-TTS path
    # once after the final reply. One turn -> one audio URL -> one playback claim.
    # Latency is deliberately secondary to deterministic, non-duplicated speech.
    if reply:
        path = tts(reply)
        audio_url = register_audio(path)
        if first_voice_ms is None:
            first_voice_ms = round((time.monotonic() - started) * 1000)
        emit({
            "type": "audio",
            "seq": audio_seq,
            "text": reply,
            "audioUrl": audio_url,
            "streaming": False,
            "latencyMs": {"firstText": first_text_ms, "firstVoice": first_voice_ms},
        })

    reply_attachments = _new_returned_attachments(before_transfers, transfer_root)
    if _should_create_first_turn_title(requested_conversation, new_conversation, title_path):
        try:
            ensure_conversation_title(key, transcript, title_path)
        except (OSError, json.JSONDecodeError):
            pass
    if reply_attachments:
        try:
            rows = history(key)
            assistant_id = _latest_assistant_message_id(rows)
            if assistant_id:
                store_attachment_metadata(key, assistant_id, reply_attachments, metadata_path)
        except (OSError, RuntimeError, json.JSONDecodeError):
            pass

    total_ms = round((time.monotonic() - started) * 1000)
    final_ms = round((final_observed - stt_done) * 1000)
    result = {
        "conversationKey": key,
        "transcript": transcript,
        "reply": reply,
        "replyAttachments": _safe_attachment_metadata(reply_attachments),
        "toolTrace": tool_trace,
        "uiHints": ui_hints_from_activity(tool_trace, reply_attachments),
        "latencyMs": {
            "stt": stt_ms,
            "firstText": first_text_ms,
            "firstVoice": first_voice_ms,
            "finalObserved": final_ms,
            "total": total_ms,
        },
    }
    emit({"type": "final", **result})
    return result


def _safe_attachment_metadata(attachments: list[dict[str, object]]) -> list[dict[str, object]]:
    safe: list[dict[str, object]] = []
    for attachment in attachments[:6]:
        if not isinstance(attachment, dict):
            continue
        file_name = attachment.get("fileName") if isinstance(attachment.get("fileName"), str) else "附件"
        mime_type = attachment.get("mimeType") if isinstance(attachment.get("mimeType"), str) else "application/octet-stream"
        size = attachment.get("sizeBytes") if isinstance(attachment.get("sizeBytes"), int) and attachment.get("sizeBytes") >= 0 else None
        item: dict[str, object] = {"fileName": file_name[:180], "mimeType": mime_type[:120], "sizeBytes": size}
        transfer_id = attachment.get("transferId")
        if isinstance(transfer_id, str) and TRANSFER_ID.fullmatch(transfer_id):
            item["transferId"] = transfer_id
        safe.append(item)
    return safe


def _attachment_record_key(conversation: str, message_id: str) -> str:
    return f"{conversation}::{message_id}"


def _read_attachment_registry(path: Path = ATTACHMENT_META_PATH) -> dict[str, object]:
    if not path.exists() or path.is_symlink():
        return {"version": 1, "messages": {}}
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "messages": {}}
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("messages"), dict):
        return {"version": 1, "messages": {}}
    return payload


def _write_attachment_registry(payload: dict[str, object], path: Path = ATTACHMENT_META_PATH) -> None:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise OSError("attachment metadata path must not be a symlink")
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, prefix=path.name + ".", delete=False) as handle:
            temp_name = handle.name
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def store_attachment_metadata(conversation: str, message_id: str, attachments: list[dict[str, object]],
                              path: Path = ATTACHMENT_META_PATH) -> bool:
    if not message_id or not attachments:
        return False
    safe = _safe_attachment_metadata(attachments)
    if not safe:
        return False
    with ATTACHMENT_META_LOCK:
        payload = _read_attachment_registry(path)
        messages = payload.setdefault("messages", {})
        if not isinstance(messages, dict):
            messages = {}
            payload["messages"] = messages
        messages[_attachment_record_key(conversation, message_id)] = {
            "attachments": safe,
            "storedAt": int(time.time()),
        }
        if len(messages) > MAX_ATTACHMENT_META_RECORDS:
            ordered = sorted(
                messages.items(),
                key=lambda item: item[1].get("storedAt", 0) if isinstance(item[1], dict) else 0,
            )
            for key, _value in ordered[:len(messages) - MAX_ATTACHMENT_META_RECORDS]:
                messages.pop(key, None)
        _write_attachment_registry(payload, path)
    return True


def load_attachment_metadata(conversation: str, message_id: str, path: Path = ATTACHMENT_META_PATH) -> list[dict[str, object]]:
    if not message_id:
        return []
    with ATTACHMENT_META_LOCK:
        payload = _read_attachment_registry(path)
    messages = payload.get("messages")
    if not isinstance(messages, dict):
        return []
    item = messages.get(_attachment_record_key(conversation, message_id))
    if not isinstance(item, dict) or not isinstance(item.get("attachments"), list):
        return []
    return _safe_attachment_metadata(item["attachments"])


def _latest_user_message_id(messages: list[dict[str, object]], expected_text: str) -> str:
    latest = ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        text = message.get("text") if isinstance(message.get("text"), str) else ""
        message_id = message.get("messageId") if isinstance(message.get("messageId"), str) else ""
        if not message_id:
            continue
        if not latest:
            latest = message_id
        if text.strip() == expected_text.strip():
            return message_id
    # The Bridge serializes Gateway turns. If the deployed Gateway normalizes a
    # file-only user message's visible text, the latest anchored user row is still
    # the just-completed chat turn.
    return latest

def _latest_assistant_message_id(messages: list[dict[str, object]]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            message_id = message.get("messageId")
            if isinstance(message_id, str) and message_id:
                return message_id
    return ""


def _returned_transfer_ids(root: Path = TRANSFER_ROOT) -> set[str]:
    return {
        item["transferId"]
        for item in list_returned_files(root=root, limit=100, include_hidden=True)
        if isinstance(item.get("transferId"), str)
    }


def _new_returned_attachments(before: set[str], root: Path = TRANSFER_ROOT) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for item in reversed(list_returned_files(root=root, limit=100, include_hidden=True)):
        transfer_id = item.get("transferId")
        if not isinstance(transfer_id, str) or transfer_id in before:
            continue
        filename = item.get("filename") if isinstance(item.get("filename"), str) else "returned-file"
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        out.append({
            "fileName": filename[:180],
            "mimeType": mime_type[:120],
            "sizeBytes": item.get("size") if isinstance(item.get("size"), int) else None,
            "transferId": transfer_id,
        })
    return out[:6]


def _should_create_first_turn_title(conversation_id: str | None, requested_new: bool, title_path: Path) -> bool:
    if not requested_new or conversation_key(conversation_id) == conversation_key(MAIN_CONVERSATION_ID):
        return False
    return not bool(load_conversation_title(conversation_id or "", title_path))


def process_chat(message: object, requested_conversation: str | None, attachments: list[dict[str, object]] | None = None,
                 autumn=autumn_turn, history=GATEWAY.history, metadata_path: Path = ATTACHMENT_META_PATH,
                 title_path: Path = CONVERSATION_TITLES_PATH, new_conversation: bool = False,
                 transfer_root: Path = TRANSFER_ROOT) -> dict[str, object]:
    if not isinstance(message, str):
        raise BridgeError("MESSAGE_REQUIRED", "Message must be text", 400)
    clean = message.strip()
    safe_attachments = attachments or []
    if not clean and not safe_attachments:
        raise BridgeError("MESSAGE_REQUIRED", "Message or attachment is required", 400)
    if len(clean.encode("utf-8")) > MAX_CHAT_BYTES:
        raise BridgeError("MESSAGE_TOO_LARGE", "Message exceeds 16 KiB", 413)
    started = time.monotonic()
    key = conversation_key(requested_conversation)
    before_transfers = _returned_transfer_ids(transfer_root)
    gateway_message = clean or "请查看我附上的文件。"
    tool_trace: list[dict[str, object]] = []
    if supports_on_trace(autumn):
        reply = autumn(gateway_message, key, source="chat", attachments=safe_attachments, on_trace=tool_trace.append)
    else:
        reply = autumn(gateway_message, key, source="chat", attachments=safe_attachments)
    reply = fail_closed_presence_reply(clean, reply, tool_trace)
    reply_attachments = _new_returned_attachments(before_transfers, transfer_root)

    title_source = clean
    if not title_source and safe_attachments:
        first_name = safe_attachments[0].get("fileName")
        title_source = f"附件 {first_name}" if isinstance(first_name, str) and first_name.strip() else "附件"
    if _should_create_first_turn_title(requested_conversation, new_conversation, title_path):
        try:
            ensure_conversation_title(key, title_source, title_path)
        except (OSError, json.JSONDecodeError):
            pass

    metadata_stored = None
    rows: list[dict[str, object]] = []
    if safe_attachments or reply_attachments:
        try:
            rows = history(key)
        except (OSError, RuntimeError, json.JSONDecodeError):
            rows = []
    if safe_attachments:
        metadata_stored = False
        message_id = _latest_user_message_id(rows, gateway_message) if rows else ""
        if message_id:
            try:
                metadata_stored = store_attachment_metadata(key, message_id, safe_attachments, metadata_path)
            except (OSError, json.JSONDecodeError):
                metadata_stored = False
    if reply_attachments and rows:
        assistant_id = _latest_assistant_message_id(rows)
        if assistant_id:
            try:
                store_attachment_metadata(key, assistant_id, reply_attachments, metadata_path)
            except (OSError, json.JSONDecodeError):
                pass

    result = {
        "conversationKey": key,
        "reply": reply,
        "replyAttachments": _safe_attachment_metadata(reply_attachments),
        "toolTrace": tool_trace,
        "uiHints": ui_hints_from_activity(tool_trace, reply_attachments),
        "latencyMs": round((time.monotonic() - started) * 1000),
    }
    if metadata_stored is not None:
        result["attachmentHistoryStored"] = metadata_stored
    return result

def process_history(conversation_id: str | None, history=GATEWAY.history,
                    metadata_path: Path = ATTACHMENT_META_PATH) -> dict[str, object]:
    key = conversation_key(conversation_id)
    try:
        raw_messages = history(key)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise BridgeError("HISTORY_UNAVAILABLE", "Conversation history is unavailable", 502) from exc
    messages = []
    for message in raw_messages[:MAX_HISTORY_MESSAGES]:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            continue
        text = message.get("text") if isinstance(message.get("text"), str) else ""
        attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
        safe = _safe_attachment_metadata(attachments)
        message_id = message.get("messageId") if isinstance(message.get("messageId"), str) else ""
        if not safe and message_id:
            safe = load_attachment_metadata(key, message_id, metadata_path)
        if text.strip() or safe:
            messages.append({"role": message["role"], "text": text, "attachments": safe})
    return {"conversationKey": key, "messages": messages}


def process_main_history(history=GATEWAY.history) -> dict[str, object]:
    return process_history(MAIN_CONVERSATION_ID, history)


def _session_title(session: dict[str, object], conversation_id: str, local_title: str = "") -> str:
    if conversation_id == MAIN_CONVERSATION_ID:
        return "Main"
    for field in ("label", "preview"):
        value = session.get(field)
        if isinstance(value, str) and value.strip():
            text = value.strip().splitlines()[0]
            if field == "label" and text in {"autumn-voice-bridge", "gateway-client"}:
                continue
            return text[:42] + ("…" if len(text) > 42 else "")
    if local_title.strip():
        return local_title.strip()[:MAX_CONVERSATION_TITLE_CHARS + 1]
    return "新对话"


def process_conversations(sessions=GATEWAY.sessions, title_path: Path = CONVERSATION_TITLES_PATH,
                          ui_state_path: Path = CONVERSATION_UI_STATE_PATH, archived_only: bool = False) -> dict[str, object]:
    try:
        raw_sessions = sessions()
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        raise BridgeError("CONVERSATIONS_UNAVAILABLE", "Conversation list is unavailable", 502) from exc
    with CONVERSATION_TITLES_LOCK:
        local_titles = _read_conversation_titles(title_path)
    with CONVERSATION_UI_STATE_LOCK:
        archived = _read_conversation_ui_state(ui_state_path)
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for session in raw_sessions:
        if not isinstance(session, dict):
            continue
        conversation_id = session.get("id")
        if not isinstance(conversation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", conversation_id):
            continue
        if conversation_id in seen:
            continue
        seen.add(conversation_id)
        is_archived = conversation_id in archived
        if archived_only and conversation_id == MAIN_CONVERSATION_ID:
            continue
        if conversation_id != MAIN_CONVERSATION_ID and is_archived != archived_only:
            continue
        items.append({
            "id": conversation_id,
            "title": _session_title(
                session,
                conversation_id,
                str(local_titles.get(conversation_key(conversation_id), {}).get("title", "")),
            ),
            "preview": session.get("preview") if isinstance(session.get("preview"), str) else "",
            "updatedAt": session.get("updatedAt") if isinstance(session.get("updatedAt"), str) else "",
            "archived": is_archived,
        })
    if not archived_only and MAIN_CONVERSATION_ID not in seen:
        items.insert(0, {"id": MAIN_CONVERSATION_ID, "title": "Main", "preview": "", "updatedAt": "", "archived": False})
    elif not archived_only:
        items.sort(key=lambda item: item["id"] != MAIN_CONVERSATION_ID)
    return {"conversations": items}


def remove_conversation_title(conversation_id: str, title_path: Path = CONVERSATION_TITLES_PATH) -> None:
    key = conversation_key(conversation_id)
    with CONVERSATION_TITLES_LOCK:
        data = _read_conversation_titles(title_path)
        if key in data:
            data.pop(key, None)
            _write_conversation_titles(data, title_path)


def _validated_chat_attachments(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_CHAT_ATTACHMENTS:
        raise BridgeError("ATTACHMENTS_INVALID", f"At most {MAX_CHAT_ATTACHMENTS} attachments are allowed", 400)
    total = 0
    result: list[dict[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict) or set(raw) - {"type", "fileName", "mimeType", "content", "sizeBytes"}:
            raise BridgeError("ATTACHMENTS_INVALID", "Attachment shape is invalid", 400)
        file_name = raw.get("fileName")
        mime_type = raw.get("mimeType")
        content = raw.get("content")
        size_bytes = raw.get("sizeBytes")
        if not isinstance(file_name, str) or not file_name.strip() or len(file_name) > 180 or any(ch in file_name for ch in "\r\n\x00"):
            raise BridgeError("ATTACHMENTS_INVALID", "Attachment filename is invalid", 400)
        if not isinstance(mime_type, str) or not mime_type.strip() or len(mime_type) > 120 or mime_type.lower().startswith("video/"):
            raise BridgeError("ATTACHMENT_TYPE_NOT_ALLOWED", "Video attachments are not supported", 415)
        if not isinstance(content, str) or not content:
            raise BridgeError("ATTACHMENTS_INVALID", "Attachment content is required", 400)
        try:
            decoded = base64.b64decode(content, validate=True)
        except (ValueError, TypeError) as exc:
            raise BridgeError("ATTACHMENTS_INVALID", "Attachment content is not valid base64", 400) from exc
        actual_size = len(decoded)
        if actual_size <= 0 or actual_size > MAX_CHAT_ATTACHMENT_BYTES:
            raise BridgeError("ATTACHMENT_TOO_LARGE", "One attachment exceeds 8 MiB", 413)
        if size_bytes is not None and (not isinstance(size_bytes, int) or size_bytes != actual_size):
            raise BridgeError("ATTACHMENTS_INVALID", "Attachment size does not match content", 400)
        total += actual_size
        if total > MAX_CHAT_ATTACHMENT_TOTAL_BYTES:
            raise BridgeError("ATTACHMENTS_TOO_LARGE", "Attachments exceed 12 MiB total", 413)
        normalized_mime = mime_type.strip().lower()
        result.append({
            # OpenClaw chat.send treats image attachments as media only when
            # their declared type is image. Preserve regular file behavior for
            # non-image Companion attachments.
            "type": "image" if normalized_mime.startswith("image/") else "file",
            "fileName": file_name.strip(),
            "mimeType": normalized_mime,
            "content": content,
            "sizeBytes": actual_size,
        })
    return result


def parse_chat(body: bytes) -> tuple[object, str | None, list[dict[str, object]], bool]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("INVALID_JSON", "Invalid JSON", 400) from exc
    if not isinstance(payload, dict):
        raise BridgeError("INVALID_JSON", "JSON object required", 400)
    if set(payload) - {"message", "conversationId", "attachments", "newConversation"}:
        raise BridgeError("INVALID_JSON", "Unexpected JSON fields", 400)
    new_conversation = payload.get("newConversation", False)
    if not isinstance(new_conversation, bool):
        raise BridgeError("INVALID_JSON", "newConversation must be boolean", 400)
    return payload.get("message", ""), payload.get("conversationId"), _validated_chat_attachments(payload.get("attachments")), new_conversation


def parse_multipart(content_type: str, body: bytes) -> tuple[bytes, str, str, str | None, bool]:
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
    raw_new = fields.get("newConversation", ({}, b"0"))[1].decode("utf-8", "ignore").strip().lower()
    new_conversation = raw_new in {"1", "true", "yes"}
    return audio, file_name, mime, conversation, new_conversation


def _read_hidden_files(path: Path = HIDDEN_FILES_PATH) -> dict[str, int]:
    if not path.exists() or path.is_symlink():
        return {}
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != 1 or not isinstance(payload.get("hidden"), dict):
        return {}
    out: dict[str, int] = {}
    for transfer_id, hidden_at in payload["hidden"].items():
        if TRANSFER_ID.fullmatch(str(transfer_id)) and isinstance(hidden_at, int):
            out[str(transfer_id)] = hidden_at
    return out


def _write_hidden_files(hidden: dict[str, int], path: Path = HIDDEN_FILES_PATH) -> None:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise OSError("hidden files path must not be a symlink")
    payload = {"version": 1, "hidden": hidden}
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, prefix=path.name + ".", delete=False) as handle:
            temp_name = handle.name
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush(); os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try: Path(temp_name).unlink(missing_ok=True)
            except OSError: pass


def set_returned_file_hidden(transfer_id: str, hidden: bool, root: Path = TRANSFER_ROOT,
                             path: Path = HIDDEN_FILES_PATH) -> bool:
    # Validate against an actual completed transfer before mutating UI state.
    returned_file(transfer_id, root)
    with HIDDEN_FILES_LOCK:
        records = _read_hidden_files(path)
        if hidden:
            records[transfer_id] = int(time.time())
            if len(records) > MAX_HIDDEN_FILE_RECORDS:
                for key, _value in sorted(records.items(), key=lambda item: item[1])[:len(records)-MAX_HIDDEN_FILE_RECORDS]:
                    records.pop(key, None)
        else:
            records.pop(transfer_id, None)
        _write_hidden_files(records, path)
    return hidden


def companion_status(opener=None) -> dict[str, object]:
    request = Request(COMPANION_STATUS_URL, method="GET", headers={"Accept": "application/json"})
    try:
        open_request = opener or build_opener(ProxyHandler({})).open
        with open_request(request, timeout=4) as response:
            payload = json.loads(response.read())
        if not isinstance(payload, dict):
            raise ValueError("invalid status")
        return payload
    except (OSError, HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise BridgeError("STATUS_UNAVAILABLE", "Companion status is unavailable", 502) from exc


def list_returned_files(root: Path = TRANSFER_ROOT, limit: int = 50, include_hidden: bool = False,
                        hidden_path: Path = HIDDEN_FILES_PATH) -> list[dict[str, object]]:
    if not root.is_dir():
        return []
    with HIDDEN_FILES_LOCK:
        hidden_ids = _read_hidden_files(hidden_path)
    items = []
    for child in root.iterdir():
        if not child.is_dir() or child.is_symlink() or not TRANSFER_ID.fullmatch(child.name):
            continue
        meta = child / "meta.json"
        data = child / "data.bin"
        if not meta.is_file() or meta.is_symlink() or not data.is_file() or data.is_symlink():
            continue
        try:
            payload = json.loads(meta.read_text("utf-8"))
            resolved = data.resolve(); resolved.relative_to(root.resolve())
            size = data.stat().st_size
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("state") != "completed" or payload.get("transfer_id") != child.name:
            continue
        is_hidden = child.name in hidden_ids
        if is_hidden and not include_hidden:
            continue
        filename = payload.get("filename") if isinstance(payload.get("filename"), str) and payload.get("filename").strip() else "returned-file"
        created = payload.get("created_at") if isinstance(payload.get("created_at"), str) else ""
        items.append({"transferId": child.name, "filename": filename[:180], "size": size, "createdAt": created, "hidden": is_hidden})
    items.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return items[:max(1, min(limit, 100))]

def returned_file(transfer_id: str, root: Path = TRANSFER_ROOT) -> tuple[Path, str]:
    if not TRANSFER_ID.fullmatch(transfer_id):
        raise BridgeError("FILE_NOT_FOUND", "Returned file was not found", 404)
    base = root.resolve()
    raw_folder = base / transfer_id
    if raw_folder.is_symlink():
        raise BridgeError("FILE_NOT_FOUND", "Returned file was not found", 404)
    folder = raw_folder.resolve()
    try:
        folder.relative_to(base)
    except ValueError as exc:
        raise BridgeError("FILE_NOT_FOUND", "Returned file was not found", 404) from exc
    meta_path, data_path = folder / "meta.json", folder / "data.bin"
    if not meta_path.is_file() or meta_path.is_symlink() or not data_path.is_file() or data_path.is_symlink():
        raise BridgeError("FILE_NOT_FOUND", "Returned file was not found", 404)
    try:
        meta = json.loads(meta_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError("FILE_NOT_FOUND", "Returned file was not found", 404) from exc
    if not isinstance(meta, dict) or meta.get("state") != "completed" or meta.get("transfer_id") != transfer_id:
        raise BridgeError("FILE_NOT_FOUND", "Returned file was not found", 404)
    filename = meta.get("filename") if isinstance(meta.get("filename"), str) and meta.get("filename").strip() else "returned-file"
    return data_path, filename[:180]


def download_content_disposition(filename: str) -> str:
    clean = filename.replace("\r", "").replace("\n", "").strip() or "returned-file"
    fallback = "".join(ch if 32 <= ord(ch) < 127 and ch not in '"\\;' else "_" for ch in clean)
    fallback = fallback[:120].strip(" .") or "returned-file"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(clean, safe='')}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass  # Do not log transcript, paths, headers, or credentials.

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    def begin_ndjson(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def emit(payload: dict[str, object]) -> None:
            data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            self.wfile.write(data)
            self.wfile.flush()
        return emit

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"ok": True, "listen": "loopback"})
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/api/conversations":
            try:
                archived_only = parse_qs(parsed.query).get("archived", [""])[0] == "1"
                self.send_json(200, process_conversations(archived_only=archived_only))
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            return
        if parsed.path == "/api/conversation-ui-state":
            with CONVERSATION_UI_STATE_LOCK:
                archived = _read_conversation_ui_state()
            self.send_json(200, {"archived": archived})
            return
        if self.path.startswith("/api/diagnostics/effective-tools"):
            try:
                query = parse_qs(urlsplit(self.path).query)
                requested = query.get("conversationId", [MAIN_CONVERSATION_ID])[0]
                safe = re.sub(r"[^A-Za-z0-9_-]", "", requested or "")[:80] or MAIN_CONVERSATION_ID
                tools = GATEWAY.effective_tools(safe)
                approved = ["jarvis_search_files", "jarvis_list_directory", "jarvis_system_status", "autumn_nodes"]
                self.send_json(200, {"conversationId": safe, "tools": tools, "approvedWindowsTools": {name: name in tools for name in approved}})
            except (OSError, RuntimeError, json.JSONDecodeError) as exc:
                self.send_json(502, {"error": "EFFECTIVE_TOOLS_UNAVAILABLE", "message": str(exc)[:160]})
            return
        parsed = urlsplit(self.path)
        request_path = parsed.path
        if request_path == "/api/vision/casts":
            self.send_json(200, {"casts": list_vision_casts()})
            return
        signal_match = re.fullmatch(r"/api/vision/casts/(vc_[A-Fa-f0-9]{18})/signals", request_path)
        if signal_match:
            query = parse_qs(parsed.query)
            target = query.get("for", [""])[0]
            try:
                after = max(0, int(query.get("after", ["0"])[0]))
                self.send_json(200, poll_vision_signals(signal_match.group(1), target, after))
            except (ValueError, BridgeError) as exc:
                if isinstance(exc, BridgeError):
                    self.send_json(exc.status, {"error": exc.code, "message": exc.message})
                else:
                    self.send_json(400, {"error": "VISION_SIGNAL_INVALID", "message": "Invalid signal cursor"})
            return
        if request_path == "/api/companion/status":
            try:
                payload = companion_status()
                payload["statusAvailable"] = True
            except BridgeError:
                payload = {"nodes": [], "windowsDataAvailable": False, "workersPaused": None, "jobs": [], "approvals": [], "statusAvailable": False}
            payload["files"] = list_returned_files()
            self.send_json(200, payload)
            return
        if request_path == "/api/files/returned":
            include_hidden = parse_qs(parsed.query).get("includeHidden", ["0"])[0] == "1"
            files = list_returned_files(include_hidden=include_hidden)
            self.send_json(200, {"files": files})
            return
        file_match = re.fullmatch(r"/api/files/returned/([A-Za-z0-9_-]{16,80})", request_path)
        if file_match:
            try:
                path, filename = returned_file(file_match.group(1))
                data = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(filename)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", download_content_disposition(filename))
                self.send_header("Cache-Control", "no-store")
                self.end_headers(); self.wfile.write(data)
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except OSError:
                self.send_json(404, {"error": "FILE_NOT_FOUND", "message": "Returned file was not found"})
            return
        history_match = re.fullmatch(r"/api/conversations/([A-Za-z0-9_-]{1,80})/history", self.path)
        if history_match:
            try:
                self.send_json(200, process_history(history_match.group(1)))
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            return
        if self.path == "/" or self.path == "/index.html":
            data = (ROOT / "index.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/continuous_voice.mjs":
            data = (ROOT / "continuous_voice.mjs").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/barge_in.mjs":
            data = (ROOT / "barge_in.mjs").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/voice_entry.mjs":
            data = (ROOT / "voice_entry.mjs").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/eyes.mjs":
            data = (ROOT / "eyes.mjs").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/spatial_shell.mjs":
            data = (ROOT / "spatial_shell.mjs").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path == "/sw.js":
            data = (ROOT / "sw.js").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        static = {"/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"), "/favicon.ico": ("icons/autumn-192.png", "image/png"), "/icons/autumn-192.png": ("icons/autumn-192.png", "image/png"), "/icons/autumn-512.png": ("icons/autumn-512.png", "image/png"), "/assets/afterglow-home.webp": ("assets/afterglow-home.webp", "image/webp")}
        if self.path in static:
            name, content_type = static[self.path]; data = (ROOT / name).read_bytes()
            self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(data); return
        if self.path.startswith("/api/audio-stream/"):
            token = self.path.rsplit("/", 1)[-1]
            with AUDIO_STREAMS_LOCK:
                stream = AUDIO_STREAMS.get(token)
            if stream is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Accept-Ranges", "none")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                for chunk in stream.iter_chunks():
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                stream.cancel()
            finally:
                with AUDIO_STREAMS_LOCK:
                    AUDIO_STREAMS.pop(token, None)
            return
        if self.path.startswith("/api/audio/"):
            item = AUDIOS.get(self.path.rsplit("/", 1)[-1])
            if not item or not item[0].is_file(): self.send_error(404); return
            data = item[0].read_bytes()
            self.send_response(200); self.send_header("Content-Type", "audio/mpeg"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data); return
        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        request_path = parsed.path
        if request_path == "/api/vision/casts":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096 or "application/json" not in self.headers.get("Content-Type", "").lower():
                    raise BridgeError("INVALID_JSON", "JSON body required", 400)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) - {"label"}:
                    raise BridgeError("INVALID_JSON", "Invalid vision cast request", 400)
                self.send_json(201, create_vision_cast(str(payload.get("label") or "")))
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except json.JSONDecodeError:
                self.send_json(400, {"error": "INVALID_JSON", "message": "Invalid JSON"})
            return
        signal_match = re.fullmatch(r"/api/vision/casts/(vc_[A-Fa-f0-9]{18})/signals", request_path)
        if signal_match:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 36_000 or "application/json" not in self.headers.get("Content-Type", "").lower():
                    raise BridgeError("INVALID_JSON", "JSON body required", 400)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {"role", "type", "payload"}:
                    raise BridgeError("VISION_SIGNAL_INVALID", "Invalid vision signal", 400)
                seq = push_vision_signal(signal_match.group(1), payload["role"], payload["type"], payload["payload"])
                self.send_json(200, {"ok": True, "seq": seq})
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except json.JSONDecodeError:
                self.send_json(400, {"error": "INVALID_JSON", "message": "Invalid JSON"})
            return
        if self.path == "/api/presence/touch":
            touch_phone_presence()
            self.send_json(200, {"ok": True})
            return
        visibility_match = re.fullmatch(r"/api/files/returned/([A-Za-z0-9_-]{16,80})/visibility", self.path)
        if visibility_match:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1024 or "application/json" not in self.headers.get("Content-Type", "").lower():
                    raise BridgeError("INVALID_JSON", "JSON body required", 400)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {"hidden"} or not isinstance(payload.get("hidden"), bool):
                    raise BridgeError("INVALID_JSON", "hidden boolean required", 400)
                hidden = set_returned_file_hidden(visibility_match.group(1), payload["hidden"])
                self.send_json(200, {"ok": True, "hidden": hidden})
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except (OSError, json.JSONDecodeError):
                self.send_json(500, {"error": "VISIBILITY_FAILED", "message": "File visibility update failed"})
            return
        if self.path == "/api/barge-intent":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_BARGE_INTENT_BYTES + 65536:
                    raise BridgeError("BARGE_INTENT_TOO_LARGE", "Interruption candidate exceeds 2 MiB", 413)
                audio, name, mime, _requested, _new_conversation = parse_multipart(
                    self.headers.get("Content-Type", ""), self.rfile.read(length)
                )
                self.send_json(200, process_barge_intent(audio, name, mime))
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except Exception:
                self.send_json(500, {"error": "BARGE_INTENT_FAILED", "message": "Interruption intent check failed"})
            return
        if self.path == "/api/chat":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_CHAT_REQUEST_BYTES:
                    raise BridgeError("MESSAGE_TOO_LARGE", "Chat request is too large", 413)
                if "application/json" not in self.headers.get("Content-Type", "").lower():
                    raise BridgeError("INVALID_JSON", "JSON body required", 400)
                message, requested, attachments, new_conversation = parse_chat(self.rfile.read(length))
                result = process_chat(message, requested, attachments, new_conversation=new_conversation)
                touch_phone_presence()  # Non-critical telemetry; failure must not affect chat.
                self.send_json(200, result)
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except Exception:
                self.send_json(500, {"error": "INTERNAL_ERROR", "message": "Chat failed"})
            return
        archive_match = re.fullmatch(r"/api/conversations/([A-Za-z0-9_-]{1,80})/(archive|restore)", request_path)
        if archive_match:
            try:
                conversation_id, action = archive_match.groups()
                title = ""
                if action == "archive":
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 1024 or "application/json" not in self.headers.get("Content-Type", "").lower():
                        raise BridgeError("INVALID_JSON", "Archive metadata required", 400)
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict) or set(payload) != {"title"} or not isinstance(payload["title"], str):
                        raise BridgeError("INVALID_JSON", "Archive title required", 400)
                    title = payload["title"]
                    self.send_json(200, process_archive_conversation(conversation_id, title))
                else:
                    self.send_json(200, process_restore_conversation(conversation_id))
            except BridgeError as exc:
                self.send_json(exc.status, {"error": exc.code, "message": exc.message})
            except (OSError, json.JSONDecodeError):
                self.send_json(500, {"error": "CONVERSATION_UI_STATE_FAILED", "message": "Conversation archive update failed"})
            return
        if self.path == "/api/turn-stream":
            emit = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_AUDIO_BYTES + 65536:
                    raise BridgeError("AUDIO_TOO_LARGE", "Audio exceeds 20 MiB", 413)
                audio, name, mime, requested, new_conversation = parse_multipart(
                    self.headers.get("Content-Type", ""), self.rfile.read(length)
                )
                emit = self.begin_ndjson()
                process_turn_stream(audio, name, mime, requested, emit, new_conversation=new_conversation)
                touch_phone_presence()
            except BridgeError as exc:
                if emit is None:
                    self.send_json(exc.status, {"error": exc.code, "message": exc.message})
                else:
                    try:
                        emit({"type": "error", "error": exc.code, "message": exc.message})
                    except OSError:
                        pass
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                if emit is None:
                    self.send_json(500, {"error": "INTERNAL_ERROR", "message": "Voice Bridge failed"})
                else:
                    try:
                        emit({"type": "error", "error": "INTERNAL_ERROR", "message": "Voice Bridge failed"})
                    except OSError:
                        pass
            return
        if self.path != "/api/turn": self.send_error(404); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_AUDIO_BYTES + 65536: raise BridgeError("AUDIO_TOO_LARGE", "Audio exceeds 20 MiB", 413)
            audio, name, mime, requested, new_conversation = parse_multipart(self.headers.get("Content-Type", ""), self.rfile.read(length))
            result = process_turn(audio, name, mime, requested, new_conversation=new_conversation)
            touch_phone_presence()  # Non-critical telemetry; failure must not affect the turn.
            self.send_json(200, result)
        except BridgeError as exc:
            self.send_json(exc.status, {"error": exc.code, "message": exc.message})
        except Exception:
            self.send_json(500, {"error": "INTERNAL_ERROR", "message": "Voice Bridge failed"})


    def do_DELETE(self) -> None:
        parsed = urlsplit(self.path)
        request_path = parsed.path
        cast_match = re.fullmatch(r"/api/vision/casts/(vc_[A-Fa-f0-9]{18})", request_path)
        if cast_match:
            self.send_json(200, {"ok": True, "closed": close_vision_cast(cast_match.group(1))})
            return
        self.send_error(404)


if __name__ == "__main__":
    assert_loopback(HOST)
    MEDIA.mkdir(mode=0o700, exist_ok=True)
    GATEWAY.start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

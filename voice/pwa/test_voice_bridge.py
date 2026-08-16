import base64, json, os, sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import voice_bridge as bridge

class VoiceBridgeTests(unittest.TestCase):
    def test_loopback_only(self):
        bridge.assert_loopback("127.0.0.1")
        with self.assertRaises(ValueError): bridge.assert_loopback("0.0.0.0")

    def test_stt_failure_does_not_call_autumn(self):
        called = []
        def stt(*_): raise bridge.BridgeError("SILICONFLOW_FAILED", "failed")
        with self.assertRaises(bridge.BridgeError): bridge.process_turn(b"a", "a.webm", "audio/webm", "x", stt, lambda *_: called.append(True), lambda *_: Path("x"))
        self.assertEqual(called, [])

    def test_direct_gateway_uses_conversation_and_returns_final_text(self):
        class FakeGateway:
            def __init__(self): self.calls = []
            def turn(self, message, key, source, attachments=None): self.calls.append((message, key, source, attachments or [])); return '收到。'
        gateway = FakeGateway()
        self.assertEqual(bridge.autumn_turn('你好', 'companion:main', gateway), '收到。')
        self.assertEqual(gateway.calls, [('你好', 'companion:main', 'voice', [])])

    def test_gateway_failure_is_explicit(self):
        class FailedGateway:
            def turn(self, *_): raise RuntimeError('disconnected')
        with self.assertRaisesRegex(bridge.BridgeError, 'Gateway') as caught:
            bridge.autumn_turn('你好', 'voice:same', FailedGateway())
        self.assertEqual(caught.exception.code, 'GATEWAY_FAILED')

    def test_conversation_key_is_stable_and_independent_of_runtime(self):
        self.assertEqual(bridge.conversation_key('main'), 'companion:main')
        self.assertEqual(bridge.conversation_key('main'), 'companion:main')
        self.assertEqual(bridge.conversation_key('c_project_a'), 'companion:c_project_a')
        self.assertNotEqual(bridge.conversation_key('main'), bridge.conversation_key('c_project_a'))
        self.assertNotIn('voice:', bridge.conversation_key('main'))

    def test_default_conversation_is_main_and_label_is_not_identity(self):
        self.assertEqual(bridge.conversation_key(None), 'companion:main')
        self.assertEqual(bridge.conversation_key('c_opaque_id'), 'companion:c_opaque_id')

    def test_process_turn_uses_main_conversation_not_runtime_identity(self):
        captured = []
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'reply.mp3'; output.write_bytes(b'a')
            result = bridge.process_turn(
                b'a', 'a.webm', 'audio/webm', 'main',
                lambda *_: '你好',
                lambda _text, key: captured.append(key) or '收到。',
                lambda *_: output,
            )
        self.assertEqual(captured, ['companion:main'])
        self.assertEqual(result['conversationKey'], 'companion:main')
        self.assertNotIn('sessionKey', result)

    def test_tts_failure_is_explicit(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'synthesis'):
            bridge.process_turn(b"a", "a.webm", "audio/webm", "x", lambda *_: '你好', lambda *_: '回复', lambda *_: (_ for _ in ()).throw(bridge.BridgeError('XIAOMI_TTS_FAILED', 'synthesis failed')))

    def test_public_response_has_no_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'a.mp3'; p.write_bytes(b'a')
            result = bridge.process_turn(b"a", "a.webm", "audio/webm", "x", lambda *_: '你好', lambda *_: '回复', lambda *_: p)
        self.assertNotIn('API_KEY', repr(result)); self.assertNotIn('SILICONFLOW', repr(result)); self.assertNotIn('XIAOMI', repr(result))

    def test_phone_presence_touch_is_best_effort(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return False
        self.assertTrue(bridge.touch_phone_presence(lambda *_args, **_kwargs: Response()))
        self.assertFalse(bridge.touch_phone_presence(lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError())))

    def test_service_worker_is_a_static_route(self):
        source = Path(bridge.__file__).read_text(encoding="utf-8")
        self.assertIn('self.path == "/sw.js"', source)
        self.assertIn('"sw.js"', source)

    def test_afterglow_background_is_an_allowlisted_static_route(self):
        source = Path(bridge.__file__).read_text(encoding="utf-8")
        self.assertIn('"/assets/afterglow-home.webp"', source)
        self.assertIn('"assets/afterglow-home.webp", "image/webp"', source)

    def test_main_chat_uses_stable_key_without_stt_or_tts(self):
        calls = []
        result = bridge.process_chat(
            '你好', 'main', [],
            lambda message, key, source, attachments=None: calls.append((message, key, source, attachments or [])) or '收到。',
        )
        self.assertEqual(calls, [('你好', 'companion:main', 'chat', [])])
        self.assertEqual(result['conversationKey'], 'companion:main')
        self.assertEqual(result['reply'], '收到。')
        self.assertIsInstance(result['latencyMs'], int)

    def test_chat_rejects_empty_invalid_json_and_oversize(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'required') as caught:
            bridge.process_chat('   ', 'main')
        self.assertEqual(caught.exception.code, 'MESSAGE_REQUIRED')
        with self.assertRaisesRegex(bridge.BridgeError, 'Invalid JSON') as caught:
            bridge.parse_chat(b'{')
        self.assertEqual(caught.exception.code, 'INVALID_JSON')
        with self.assertRaisesRegex(bridge.BridgeError, '16 KiB') as caught:
            bridge.process_chat('x' * (bridge.MAX_CHAT_BYTES + 1), 'main')
        self.assertEqual(caught.exception.code, 'MESSAGE_TOO_LARGE')

    def test_chat_gateway_failure_is_safe(self):
        class FailedGateway:
            def turn(self, *_): raise RuntimeError('disconnected')
        with self.assertRaisesRegex(bridge.BridgeError, 'Gateway') as caught:
            bridge.process_chat('你好', 'main', [], lambda message, key, source, attachments=None: bridge.autumn_turn(message, key, FailedGateway(), source, attachments))
        self.assertEqual(caught.exception.code, 'GATEWAY_FAILED')

    def test_main_history_is_bounded_and_filters_gateway_messages(self):
        raw = [
            {'role': 'user', 'text': '你好'},
            {'role': 'assistant', 'text': '收到。'},
            {'role': 'tool', 'text': 'private tool payload'},
            {'role': 'assistant', 'text': ''},
        ]
        result = bridge.process_main_history(lambda key: raw)
        self.assertEqual(result['conversationKey'], 'companion:main')
        self.assertEqual(result['messages'], [{**raw[0], 'attachments': []}, {**raw[1], 'attachments': []}])

    def test_main_history_failure_is_safe(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'history') as caught:
            bridge.process_main_history(lambda _key: (_ for _ in ()).throw(RuntimeError('down')))
        self.assertEqual(caught.exception.code, 'HISTORY_UNAVAILABLE')

    def test_generic_history_route_is_explicit(self):
        source = Path(bridge.__file__).read_text(encoding='utf-8')
        self.assertIn('/api/conversations/', source)
        self.assertIn('process_history(history_match.group(1))', source)

    def test_conversation_list_is_openclaw_native_and_main_first(self):
        rows = [
            {'id': 'c_project', 'label': 'FPGA 学习', 'preview': '继续桶形移位器', 'updatedAt': '2026-08-15T12:00:00Z'},
            {'id': 'main', 'label': '', 'preview': 'Main preview', 'updatedAt': '2026-08-15T13:00:00Z'},
            {'id': 'bad/id', 'label': 'reject'},
        ]
        result = bridge.process_conversations(lambda: rows)
        self.assertEqual([item['id'] for item in result['conversations']], ['main', 'c_project'])
        self.assertEqual(result['conversations'][0]['title'], 'Main')
        self.assertEqual(result['conversations'][1]['title'], 'FPGA 学习')

    def test_conversation_title_ignores_gateway_client_display_name(self):
        rows = [
            {
                'id': 'c_named',
                'label': 'autumn-voice-bridge',
                'preview': '继续学习桶形移位器',
                'updatedAt': '2026-08-16T07:00:00Z',
            },
        ]
        result = bridge.process_conversations(lambda: rows)
        self.assertEqual(result['conversations'][1]['title'], '继续学习桶形移位器')

    def test_auto_conversation_title_is_compact_and_free(self):
        self.assertEqual(bridge._auto_conversation_title("我想继续学习 FPGA 的桶形移位器。"), "FPGA 的桶形移位器")
        self.assertEqual(bridge._auto_conversation_title("帮我规划一下明天的数字电路复习。"), "明天的数字电路复习")
        self.assertEqual(bridge._auto_conversation_title("Please help me understand Verilog FSM design."), "Verilog FSM design")

    def test_conversation_title_sidecar_fills_empty_openclaw_title(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "titles.json"
            self.assertTrue(bridge.ensure_conversation_title("companion:c_auto", "我想继续学习 FPGA 的桶形移位器。", path))
            self.assertFalse(bridge.ensure_conversation_title("companion:c_auto", "第二条消息不应改名。", path))
            rows = [{"id":"c_auto","label":"","preview":"","updatedAt":"2026-08-16T08:00:00Z"}]
            result = bridge.process_conversations(lambda: rows, path)
            self.assertEqual(result["conversations"][1]["title"], "FPGA 的桶形移位器")
            raw = path.read_text("utf-8")
            self.assertNotIn("我想继续学习", raw)
            self.assertNotIn("第二条消息", raw)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_process_chat_creates_title_only_for_secondary_conversation(self):
        with tempfile.TemporaryDirectory() as temp:
            title_path = Path(temp) / "titles.json"
            result = bridge.process_chat(
                "帮我规划一下明天的数字电路复习。", "c_chat", [],
                lambda *_args, **_kwargs: "好。",
                title_path=title_path, new_conversation=True,
            )
            self.assertEqual(result["conversationKey"], "companion:c_chat")
            self.assertEqual(bridge.load_conversation_title("c_chat", title_path), "明天的数字电路复习")

    def test_existing_untitled_conversation_is_not_retroactively_retitled(self):
        with tempfile.TemporaryDirectory() as temp:
            title_path = Path(temp) / "titles.json"
            bridge.process_chat(
                "这是旧对话里的后续消息。", "c_existing", [],
                lambda *_args, **_kwargs: "继续。",
                title_path=title_path, new_conversation=False,
            )
            self.assertEqual(bridge.load_conversation_title("c_existing", title_path), "")

    def test_conversation_list_adds_main_when_missing(self):
        result = bridge.process_conversations(lambda: [{'id': 'c_other', 'preview': 'hello'}])
        self.assertEqual(result['conversations'][0]['id'], 'main')
        self.assertEqual(result['conversations'][1]['id'], 'c_other')

    def test_conversation_list_failure_is_safe(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'Conversation list') as caught:
            bridge.process_conversations(lambda: (_ for _ in ()).throw(RuntimeError('down')))
        self.assertEqual(caught.exception.code, 'CONVERSATIONS_UNAVAILABLE')

    def test_chat_attachments_validate_and_forward_without_stt_tts(self):
        content = base64.b64encode(b"hello file").decode("ascii")
        raw = json.dumps({
            "conversationId": "main", "message": "看看这个",
            "attachments": [{"type":"file","fileName":"note.txt","mimeType":"text/plain","content":content,"sizeBytes":10}],
        }).encode()
        message, conversation, attachments, new_conversation = bridge.parse_chat(raw)
        self.assertFalse(new_conversation)
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            result = bridge.process_chat(
                message, conversation, attachments,
                lambda text, key, source, attachments=None: calls.append((text, key, source, attachments)) or "看到了。",
                lambda _key: [{"role":"user","text":"看看这个","messageId":"m-upload-1","attachments":[]}],
                Path(temp) / "attachments.json",
            )
        self.assertEqual(result["reply"], "看到了。")
        self.assertEqual(calls[0][1:3], ("companion:main", "chat"))
        self.assertEqual(calls[0][3][0]["fileName"], "note.txt")
        self.assertEqual(calls[0][3][0]["content"], content)

    def test_file_only_chat_uses_gateway_fallback_and_rejects_video(self):
        content = base64.b64encode(b"abc").decode("ascii")
        attachment = {"type":"file","fileName":"a.txt","mimeType":"text/plain","content":content,"sizeBytes":3}
        seen = []
        with tempfile.TemporaryDirectory() as temp:
            result = bridge.process_chat(
                "", "main", [attachment],
                lambda text, *_args, **_kwargs: seen.append(text) or "OK",
                lambda _key: [{"role":"user","text":"请查看我附上的文件。","messageId":"m-file-only","attachments":[]}],
                Path(temp) / "attachments.json",
            )
        self.assertTrue(result["attachmentHistoryStored"])
        self.assertEqual(seen, ["请查看我附上的文件。"])
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.parse_chat(json.dumps({"message":"x","attachments":[{**attachment,"mimeType":"video/mp4"}]}).encode())
        self.assertEqual(caught.exception.code, "ATTACHMENT_TYPE_NOT_ALLOWED")

    def test_attachment_limits_and_invalid_base64(self):
        item = {"type":"file","fileName":"a.txt","mimeType":"text/plain","content":"%%%","sizeBytes":1}
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.parse_chat(json.dumps({"message":"x","attachments":[item]}).encode())
        self.assertEqual(caught.exception.code, "ATTACHMENTS_INVALID")
        many = [{"type":"file","fileName":f"{i}.txt","mimeType":"text/plain","content":base64.b64encode(b"a").decode(),"sizeBytes":1} for i in range(4)]
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.parse_chat(json.dumps({"message":"x","attachments":many}).encode())
        self.assertEqual(caught.exception.code, "ATTACHMENTS_INVALID")

    def test_history_preserves_bounded_safe_attachment_metadata(self):
        raw = [{"role":"user","text":"","attachments":[{"fileName":"report.pdf","mimeType":"application/pdf","sizeBytes":1234,"content":"secret"}]}]
        result = bridge.process_history("main", lambda _key: raw)
        self.assertEqual(result["messages"], [{"role":"user","text":"","attachments":[{"fileName":"report.pdf","mimeType":"application/pdf","sizeBytes":1234}]}])
        self.assertNotIn("content", repr(result))

    def test_attachment_sidecar_restores_metadata_without_copying_content(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "attachments.json"
            attachments = [{"fileName":"note.txt","mimeType":"text/plain","sizeBytes":5,"content":"SECRET-BASE64"}]
            self.assertTrue(bridge.store_attachment_metadata("companion:main", "m-1", attachments, path))
            raw_text = path.read_text("utf-8")
            self.assertNotIn("SECRET-BASE64", raw_text)
            result = bridge.process_history(
                "main",
                lambda _key: [{"role":"user","text":"看看附件","messageId":"m-1","attachments":[]}],
                path,
            )
            self.assertEqual(result["messages"][0]["attachments"], [
                {"fileName":"note.txt","mimeType":"text/plain","sizeBytes":5}
            ])
            self.assertNotIn("messageId", repr(result))

    def test_attachment_message_id_falls_back_to_latest_user_when_gateway_normalizes_text(self):
        rows = [
            {"role":"user","text":"older","messageId":"m-old"},
            {"role":"assistant","text":"reply","messageId":"m-a"},
            {"role":"user","text":"[normalized attachment]","messageId":"m-new"},
        ]
        self.assertEqual(bridge._latest_user_message_id(rows, "请查看我附上的文件。"), "m-new")

    def test_process_chat_records_sidecar_against_gateway_message_id(self):
        content = base64.b64encode(b"hello").decode("ascii")
        attachment = {"type":"file","fileName":"hello.txt","mimeType":"text/plain","content":content,"sizeBytes":5}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "attachments.json"
            result = bridge.process_chat(
                "读这个", "main", [attachment],
                lambda *_args, **_kwargs: "读到了。",
                lambda _key: [
                    {"role":"user","text":"更早消息","messageId":"m-old","attachments":[]},
                    {"role":"user","text":"读这个","messageId":"m-new","attachments":[]},
                    {"role":"assistant","text":"读到了。","messageId":"m-assistant","attachments":[]},
                ],
                path,
            )
            self.assertTrue(result["attachmentHistoryStored"])
            restored = bridge.load_attachment_metadata("companion:main", "m-new", path)
            self.assertEqual(restored, [{"fileName":"hello.txt","mimeType":"text/plain","sizeBytes":5}])
            self.assertEqual(bridge.load_attachment_metadata("companion:main", "m-old", path), [])

    def test_outbound_companion_transfer_becomes_clickable_assistant_attachment_and_survives_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "transfers"; root.mkdir()
            metadata_path = Path(temp) / "attachments.json"
            tid = "qrstuvwxyzABCDEF"
            def autumn(*_args, **_kwargs):
                folder = root / tid; folder.mkdir()
                (folder / "data.bin").write_text("# note", encoding="utf-8")
                (folder / "meta.json").write_text(json.dumps({
                    "transfer_id": tid, "filename": "桶形移位器.md", "size": 6,
                    "created_at": "2026-08-16T09:00:00+00:00", "state": "completed",
                }), encoding="utf-8")
                return "已经作为附件发给你。"
            rows = [
                {"role":"user","text":"发给我","messageId":"m-user","attachments":[]},
                {"role":"assistant","text":"已经作为附件发给你。","messageId":"m-assistant","attachments":[]},
            ]
            result = bridge.process_chat(
                "发给我", "c_files", [], autumn, lambda _key: rows, metadata_path=metadata_path, transfer_root=root,
            )
            self.assertEqual(result["replyAttachments"][0]["transferId"], tid)
            restored = bridge.process_history("c_files", lambda _key: rows, metadata_path)
            self.assertEqual(restored["messages"][1]["attachments"][0]["transferId"], tid)
            self.assertEqual(restored["messages"][1]["attachments"][0]["fileName"], "桶形移位器.md")

    def test_returned_file_listing_and_lookup_are_strict(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); tid = "abcdefghijklmnop"; folder = root / tid; folder.mkdir()
            (folder / "data.bin").write_bytes(b"payload")
            (folder / "meta.json").write_text(json.dumps({"transfer_id":tid,"filename":"report.pdf","size":7,"created_at":"2026-08-16T01:00:00+00:00","state":"completed"}), encoding="utf-8")
            files = bridge.list_returned_files(root)
            self.assertEqual(files[0]["transferId"], tid)
            item = bridge.returned_file(tid, root)
            self.assertEqual(item[0].read_bytes(), b"payload")
            with self.assertRaises(bridge.BridgeError): bridge.returned_file("../bad", root)

    def test_returned_file_visibility_sidecar_hides_without_deleting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "transfers"; root.mkdir()
            hidden_path = Path(temp) / "hidden.json"
            tid = "abcdefghijklmnop"; folder = root / tid; folder.mkdir()
            (folder / "data.bin").write_bytes(b"payload")
            (folder / "meta.json").write_text(json.dumps({"transfer_id":tid,"filename":"smoke.txt","size":7,"created_at":"2026-08-16T01:00:00+00:00","state":"completed"}), encoding="utf-8")
            self.assertTrue(bridge.set_returned_file_hidden(tid, True, root, hidden_path))
            self.assertEqual(bridge.list_returned_files(root, hidden_path=hidden_path), [])
            all_files = bridge.list_returned_files(root, include_hidden=True, hidden_path=hidden_path)
            self.assertEqual(all_files[0]["transferId"], tid)
            self.assertTrue(all_files[0]["hidden"])
            self.assertTrue((folder / "data.bin").is_file())
            self.assertFalse(bridge.set_returned_file_hidden(tid, False, root, hidden_path))
            self.assertEqual(bridge.list_returned_files(root, hidden_path=hidden_path)[0]["transferId"], tid)
            self.assertTrue(hidden_path.is_file())
            self.assertFalse(hidden_path.is_symlink())
            if os.name != "nt":
                self.assertEqual(hidden_path.stat().st_mode & 0o777, 0o600)

    def test_returned_file_download_header_supports_unicode_without_header_injection(self):
        header = bridge.download_content_disposition('学习路线.pdf\r\nX-Bad: yes')
        self.assertTrue(header.startswith('attachment; filename="'))
        self.assertIn("filename*=UTF-8''", header)
        self.assertIn('%E5%AD%A6%E4%B9%A0%E8%B7%AF%E7%BA%BF.pdfX-Bad%3A%20yes', header)
        self.assertNotIn('\r', header)
        self.assertNotIn('\n', header)

    def test_companion_status_proxy_is_safe(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self,*_): return False
            def read(self): return json.dumps({"nodes":[],"windowsDataAvailable":True,"workersPaused":False,"jobs":[],"approvals":[]}).encode()
        result = bridge.companion_status(lambda *_args, **_kwargs: Response())
        self.assertTrue(result["windowsDataAvailable"])
        self.assertEqual(result["jobs"], [])

if __name__ == '__main__': unittest.main()

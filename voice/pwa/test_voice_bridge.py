import sys, tempfile, unittest
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
            def turn(self, message, key, source): self.calls.append((message, key, source)); return '收到。'
        gateway = FakeGateway()
        self.assertEqual(bridge.autumn_turn('你好', 'companion:main', gateway), '收到。')
        self.assertEqual(gateway.calls, [('你好', 'companion:main', 'voice')])

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
            '你好', 'main',
            lambda message, key, source: calls.append((message, key, source)) or '收到。',
        )
        self.assertEqual(calls, [('你好', 'companion:main', 'chat')])
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
            bridge.process_chat('你好', 'main', lambda message, key, source: bridge.autumn_turn(message, key, FailedGateway(), source))
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
        self.assertEqual(result['messages'], raw[:2])

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

    def test_conversation_list_adds_main_when_missing(self):
        result = bridge.process_conversations(lambda: [{'id': 'c_other', 'preview': 'hello'}])
        self.assertEqual(result['conversations'][0]['id'], 'main')
        self.assertEqual(result['conversations'][1]['id'], 'c_other')

    def test_conversation_list_failure_is_safe(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'Conversation list') as caught:
            bridge.process_conversations(lambda: (_ for _ in ()).throw(RuntimeError('down')))
        self.assertEqual(caught.exception.code, 'CONVERSATIONS_UNAVAILABLE')

if __name__ == '__main__': unittest.main()

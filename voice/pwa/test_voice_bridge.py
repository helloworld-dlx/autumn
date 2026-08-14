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
            def turn(self, message, key): self.calls.append((message, key)); return '收到。'
        gateway = FakeGateway()
        self.assertEqual(bridge.autumn_turn('你好', 'companion:main', gateway), '收到。')
        self.assertEqual(gateway.calls, [('你好', 'companion:main')])

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

if __name__ == '__main__': unittest.main()

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

    def test_direct_gateway_uses_session_and_returns_final_text(self):
        class FakeGateway:
            def __init__(self): self.calls = []
            def turn(self, message, key): self.calls.append((message, key)); return '收到。'
        gateway = FakeGateway()
        self.assertEqual(bridge.autumn_turn('你好', 'voice:same', gateway), '收到。')
        self.assertEqual(gateway.calls, [('你好', 'voice:same')])

    def test_gateway_failure_is_explicit(self):
        class FailedGateway:
            def turn(self, *_): raise RuntimeError('disconnected')
        with self.assertRaisesRegex(bridge.BridgeError, 'Gateway') as caught:
            bridge.autumn_turn('你好', 'voice:same', FailedGateway())
        self.assertEqual(caught.exception.code, 'GATEWAY_FAILED')

    def test_session_key_reuses_id(self):
        self.assertEqual(bridge.session_key('same'), 'voice:same')
        self.assertEqual(bridge.session_key('same'), 'voice:same')

    def test_tts_failure_is_explicit(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'synthesis'):
            bridge.process_turn(b"a", "a.webm", "audio/webm", "x", lambda *_: '你好', lambda *_: '回复', lambda *_: (_ for _ in ()).throw(bridge.BridgeError('XIAOMI_TTS_FAILED', 'synthesis failed')))

    def test_public_response_has_no_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'a.mp3'; p.write_bytes(b'a')
            result = bridge.process_turn(b"a", "a.webm", "audio/webm", "x", lambda *_: '你好', lambda *_: '回复', lambda *_: p)
        self.assertNotIn('API_KEY', repr(result)); self.assertNotIn('SILICONFLOW', repr(result)); self.assertNotIn('XIAOMI', repr(result))

if __name__ == '__main__': unittest.main()

# PWA source tests

Consolidated to keep `voice/pwa/` focused on production files.

Run from `voice/pwa`:

```bash
node tests/test_voice_runtime.mjs
node tests/test_companion_ui.mjs
node tests/test_eyes.mjs
node tests/test_gateway_turn.mjs
python3 -m unittest -q test_voice_bridge.py
```

`test_voice_bridge.py` stays beside `voice_bridge.py` because it imports the Python module directly.

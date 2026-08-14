import assert from 'node:assert/strict';
import test from 'node:test';
import { ContinuousVoiceSession } from './continuous_voice.mjs';

test('quick voice turns off after playback', () => {
  const session = new ContinuousVoiceSession('runtime-quick', 'main', 'quick');
  session.start();
  session.processing();
  session.speaking();
  session.playbackEnded();
  assert.equal(session.state, 'OFF');
  assert.equal(session.shouldListen(), false);
  assert.equal(session.conversationId, 'main');
});

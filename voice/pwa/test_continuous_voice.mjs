import assert from 'node:assert/strict';
import test from 'node:test';
import { ContinuousVoiceSession } from './continuous_voice.mjs';

test('three turns reuse one session id', () => {
  const session = new ContinuousVoiceSession('same-session');
  session.start();
  const ids = [];
  for (let i = 0; i < 3; i += 1) {
    ids.push(session.sessionId);
    session.processing();
    session.speaking();
    session.playbackEnded();
  }
  assert.deepEqual(ids, ['same-session', 'same-session', 'same-session']);
  assert.equal(session.turn, 3);
});

test('stop prevents automatic listening', () => {
  const session = new ContinuousVoiceSession('s');
  session.start();
  session.processing();
  session.stop();
  session.playbackEnded();
  assert.equal(session.state, 'OFF');
  assert.equal(session.shouldListen(), false);
});

test('speaking never permits capture', () => {
  const session = new ContinuousVoiceSession('s');
  session.start();
  session.processing();
  session.speaking();
  assert.equal(session.shouldListen(), false);
});

test('idle timeout ends the session', () => {
  const session = new ContinuousVoiceSession('s');
  session.start();
  session.idleExpired();
  assert.equal(session.state, 'OFF');
  assert.equal(session.running, false);
});

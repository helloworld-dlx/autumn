import assert from 'node:assert/strict';
import test from 'node:test';
import { ContinuousVoiceSession } from './continuous_voice.mjs';

test('three turns reuse one runtime and stable conversation identity', () => {
  const session = new ContinuousVoiceSession('runtime-one', 'main');
  session.start();
  const ids = [];
  for (let i = 0; i < 3; i += 1) {
    ids.push(session.runtimeId);
    session.processing();
    session.speaking();
    session.playbackEnded();
  }
  assert.deepEqual(ids, ['runtime-one', 'runtime-one', 'runtime-one']);
  assert.equal(session.conversationId, 'main');
  assert.equal(session.turn, 3);
});

test('stop prevents automatic listening', () => {
  const session = new ContinuousVoiceSession('runtime-stop', 'main');
  session.start();
  session.processing();
  session.stop();
  session.playbackEnded();
  assert.equal(session.state, 'OFF');
  assert.equal(session.shouldListen(), false);
});

test('speaking never permits capture', () => {
  const session = new ContinuousVoiceSession('runtime-speaking', 'main');
  session.start();
  session.processing();
  session.speaking();
  assert.equal(session.shouldListen(), false);
});

test('idle timeout ends the session', () => {
  const session = new ContinuousVoiceSession('runtime-idle', 'main');
  session.start();
  session.idleExpired();
  assert.equal(session.state, 'OFF');
  assert.equal(session.running, false);
});

test('Quick and Continuous runtime IDs map to the same Main conversation', () => {
  const quickFirst = new ContinuousVoiceSession('runtime-quick-1', 'main', 'quick');
  const quickSecond = new ContinuousVoiceSession('runtime-quick-2', 'main', 'quick');
  const continuous = new ContinuousVoiceSession('runtime-continuous', 'main', 'continuous');
  assert.notEqual(quickFirst.runtimeId, quickSecond.runtimeId);
  assert.equal(quickFirst.conversationId, 'main');
  assert.equal(quickSecond.conversationId, 'main');
  assert.equal(continuous.conversationId, 'main');
});

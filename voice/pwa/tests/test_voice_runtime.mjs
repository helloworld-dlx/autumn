import assert from 'node:assert/strict';
import test from 'node:test';
import { BargeInDetector } from '../barge_in.mjs';
import { ContinuousVoiceSession } from '../continuous_voice.mjs';
import { voiceEntryFrom, isAutumnVoiceHotkey } from '../voice_entry.mjs';


// ---- merged from test_barge_in.mjs ----
{

test('sustained speech ducks before interrupting', () => {
  const detector = new BargeInDetector({ threshold: 0.03, duckMs: 240, interruptMs: 520, releaseMs: 180 });
  assert.deepEqual(detector.sample(0.04, 1000), ['speech-start']);
  assert.deepEqual(detector.sample(0.04, 1240), ['duck']);
  assert.deepEqual(detector.sample(0.04, 1520), ['interrupt']);
});

test('brief sound resets instead of interrupting', () => {
  const detector = new BargeInDetector({ threshold: 0.03, duckMs: 240, interruptMs: 520, releaseMs: 180 });
  detector.sample(0.04, 1000);
  detector.sample(0.01, 1100);
  assert.deepEqual(detector.sample(0.01, 1280), ['reset']);
  assert.deepEqual(detector.sample(0.04, 1400), ['speech-start']);
});
}

// ---- merged from test_continuous_voice.mjs ----
{

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

test('stop invalidates an in-flight generation claim', () => {
  const session = new ContinuousVoiceSession('runtime-claim', 'main');
  session.start();
  const claim = session.processing();
  assert.equal(session.isCurrent(claim), true);
  session.stop();
  assert.equal(session.isCurrent(claim), false);
});

test('a newer turn invalidates the previous turn claim', () => {
  const session = new ContinuousVoiceSession('runtime-newer', 'main');
  session.start();
  const first = session.processing();
  session.state = 'LISTENING';
  const second = session.processing();
  assert.equal(session.isCurrent(first), false);
  assert.equal(session.isCurrent(second), true);
});


test('continuous speaking permits barge-in monitoring without normal capture', () => {
  const session = new ContinuousVoiceSession('runtime-barge', 'main', 'continuous');
  session.start();
  const oldClaim = session.processing();
  session.speaking(oldClaim);
  assert.equal(session.shouldListen(), false);
  assert.equal(session.shouldMonitorBargeIn(), true);
  const interruptClaim = session.interrupt();
  assert.ok(interruptClaim);
  assert.equal(session.state, 'LISTENING');
  assert.equal(session.isCurrent(oldClaim), false);
  assert.equal(session.isCurrent(interruptClaim), true);
  assert.equal(session.conversationId, 'main');
});

test('quick mode does not open barge-in continuation', () => {
  const session = new ContinuousVoiceSession('runtime-quick-barge', 'main', 'quick');
  session.start();
  const claim = session.processing();
  session.speaking(claim);
  assert.equal(session.shouldMonitorBargeIn(), false);
  assert.equal(session.interrupt(), null);
  assert.equal(session.state, 'SPEAKING');
});
}

// ---- merged from test_quick_voice.mjs ----
{

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
}

// ---- merged from test_voice_entry.mjs ----
{

assert.deepEqual(voiceEntryFrom(''), {requested:false, mode:'continuous', autostart:false});
assert.deepEqual(voiceEntryFrom('?entry=voice&mode=continuous&autostart=1'), {requested:true, mode:'continuous', autostart:true});
assert.deepEqual(voiceEntryFrom('?entry=voice&mode=quick&autostart=true'), {requested:true, mode:'quick', autostart:true});
assert.deepEqual(voiceEntryFrom('?entry=voice&mode=quick'), {requested:true, mode:'quick', autostart:false});
assert.equal(isAutumnVoiceHotkey({ctrlKey:true, altKey:true, shiftKey:true, code:'KeyA'}), true);
assert.equal(isAutumnVoiceHotkey({ctrlKey:true, altKey:false, shiftKey:true, code:'KeyA'}), false);
console.log('voice_entry regression: PASS');
}

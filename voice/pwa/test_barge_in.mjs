import assert from 'node:assert/strict';
import test from 'node:test';
import { BargeInDetector } from './barge_in.mjs';

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

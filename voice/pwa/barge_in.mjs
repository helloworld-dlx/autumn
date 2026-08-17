export class BargeInDetector {
  constructor({ threshold = 0.032, duckMs = 240, interruptMs = 520, releaseMs = 180 } = {}) {
    this.threshold = threshold;
    this.duckMs = duckMs;
    this.interruptMs = interruptMs;
    this.releaseMs = releaseMs;
    this.reset();
  }

  reset() {
    this.speechStart = null;
    this.quietSince = null;
    this.ducked = false;
    this.interrupted = false;
  }

  sample(rms, nowMs) {
    const events = [];
    if (!Number.isFinite(rms) || !Number.isFinite(nowMs)) return events;

    if (rms >= this.threshold) {
      if (this.speechStart === null) {
        this.speechStart = nowMs;
        events.push('speech-start');
      }
      this.quietSince = null;
      const voicedMs = nowMs - this.speechStart;
      if (!this.ducked && voicedMs >= this.duckMs) {
        this.ducked = true;
        events.push('duck');
      }
      if (!this.interrupted && voicedMs >= this.interruptMs) {
        this.interrupted = true;
        events.push('interrupt');
      }
      return events;
    }

    if (this.speechStart === null || this.interrupted) return events;
    if (this.quietSince === null) this.quietSince = nowMs;
    if (nowMs - this.quietSince >= this.releaseMs) {
      this.reset();
      events.push('reset');
    }
    return events;
  }
}

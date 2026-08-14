export class ContinuousVoiceSession {
  constructor(sessionId, mode = 'continuous') {
    this.sessionId = sessionId;
    this.mode = mode;
    this.running = false;
    this.state = 'OFF';
    this.turn = 0;
  }

  start() {
    this.running = true;
    this.state = 'LISTENING';
  }

  processing() {
    if (!this.running) return;
    this.turn += 1;
    this.state = 'PROCESSING';
  }

  speaking() {
    if (this.running) this.state = 'SPEAKING';
  }

  playbackEnded() {
    if (this.mode === 'quick') this.stop();
    else this.state = this.running ? 'LISTENING' : 'OFF';
  }

  stop() {
    this.running = false;
    this.state = 'OFF';
  }

  idleExpired() {
    this.stop();
  }

  shouldListen() {
    return this.running && this.state === 'LISTENING';
  }
}

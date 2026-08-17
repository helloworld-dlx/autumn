export class ContinuousVoiceSession {
  constructor(runtimeId, conversationId = 'main', mode = 'continuous') {
    this.runtimeId = runtimeId;
    this.conversationId = conversationId;
    this.mode = mode;
    this.running = false;
    this.state = 'OFF';
    this.turn = 0;
    this.generation = 0;
  }

  start() {
    this.running = true;
    this.state = 'LISTENING';
    this.generation += 1;
    return this.claim();
  }

  processing() {
    if (!this.running) return null;
    this.turn += 1;
    this.generation += 1;
    this.state = 'PROCESSING';
    return this.claim();
  }

  speaking(claim = null) {
    if (this.running && (!claim || this.isCurrent(claim))) this.state = 'SPEAKING';
  }

  shouldMonitorBargeIn() {
    return this.running && this.mode === 'continuous' && this.state === 'SPEAKING';
  }

  interrupt() {
    if (!this.shouldMonitorBargeIn()) return null;
    this.generation += 1;
    this.state = 'LISTENING';
    return this.claim();
  }

  playbackEnded(claim = null) {
    if (claim && !this.isCurrent(claim)) return;
    if (this.mode === 'quick') this.stop();
    else this.state = this.running ? 'LISTENING' : 'OFF';
  }

  stop() {
    this.generation += 1;
    this.running = false;
    this.state = 'OFF';
  }

  idleExpired() {
    this.stop();
  }

  claim() {
    return {
      runtimeId: this.runtimeId,
      turn: this.turn,
      generation: this.generation,
    };
  }

  isCurrent(claim) {
    return Boolean(
      this.running &&
      claim &&
      claim.runtimeId === this.runtimeId &&
      claim.generation === this.generation
    );
  }

  shouldListen() {
    return this.running && this.state === 'LISTENING';
  }
}

const VOICE_QUERY_KEYS = new Set(['entry', 'mode', 'autostart']);
const VOICE_HOTKEY = Object.freeze({ctrlKey: true, altKey: true, shiftKey: true, code: 'KeyA'});

export function voiceEntryFrom(search = '') {
  const params = new URLSearchParams(String(search).replace(/^\?/, ''));
  const requested = params.get('entry') === 'voice';
  const mode = params.get('mode') === 'quick' ? 'quick' : 'continuous';
  const autostart = requested && ['1', 'true', 'yes', mode].includes((params.get('autostart') || '').toLowerCase());
  return {requested, mode, autostart};
}

export function isAutumnVoiceHotkey(event) {
  return Boolean(event && event.ctrlKey === VOICE_HOTKEY.ctrlKey && event.altKey === VOICE_HOTKEY.altKey && event.shiftKey === VOICE_HOTKEY.shiftKey && event.code === VOICE_HOTKEY.code);
}

function visibleTalkButton() {
  const candidates = [...document.querySelectorAll('[data-page="talk"]')];
  return candidates.find((node) => node.offsetParent !== null) || candidates[0] || null;
}

function selectTalkPage() {
  visibleTalkButton()?.click();
}

function selectMode(mode) {
  const button = document.querySelector(mode === 'quick' ? '#quick' : '#conversation');
  if (button && !button.disabled) button.click();
}

async function waitForConnected(timeoutMs = 5000) {
  const connectivity = document.querySelector('#connectivity');
  if (!connectivity) return false;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if ((connectivity.dataset.state || '').toLowerCase() === 'connected' || connectivity.textContent?.trim() === 'CONNECTED') return true;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return false;
}

function restoreConversationHint() {
  if (globalThis.autumnActiveConversationId) return;
  try {
    const saved = localStorage.getItem('autumnActiveConversationId');
    if (saved) globalThis.autumnActiveConversationId = saved;
  } catch {}
}

function consumeVoiceEntryQuery() {
  const url = new URL(location.href);
  let changed = false;
  for (const key of VOICE_QUERY_KEYS) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  }
  if (changed) history.replaceState(history.state, '', url.pathname + (url.search ? url.search : '') + url.hash);
}

export async function openAutumnVoice({mode = 'continuous', autostart = true} = {}) {
  restoreConversationHint();
  selectTalkPage();
  selectMode(mode);
  if (!autostart || globalThis.autumnVoiceRunning?.()) return true;
  const connected = await waitForConnected();
  if (!connected) return false;
  selectMode(mode);
  const start = document.querySelector('#start');
  if (!start || globalThis.autumnVoiceRunning?.()) return Boolean(globalThis.autumnVoiceRunning?.());
  start.click();
  await new Promise((resolve) => setTimeout(resolve, 120));
  return Boolean(globalThis.autumnVoiceRunning?.());
}

async function handleInitialEntry() {
  const entry = voiceEntryFrom(location.search);
  if (!entry.requested) return;
  consumeVoiceEntryQuery();
  await openAutumnVoice({mode: entry.mode, autostart: entry.autostart});
}

if (typeof document !== 'undefined') {
  document.addEventListener('keydown', (event) => {
    if (!isAutumnVoiceHotkey(event)) return;
    event.preventDefault();
    event.stopPropagation();
    openAutumnVoice({mode: 'continuous', autostart: true});
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', handleInitialEntry, {once: true});
  } else {
    queueMicrotask(handleInitialEntry);
  }
}

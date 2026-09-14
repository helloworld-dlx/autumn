#!/usr/bin/env node
import fs from 'node:fs';
import { once } from 'node:events';

const CONFIG_PATH = '/home/xyzlh/.openclaw/openclaw.json';
const AUTH_MODULE = 'file:///home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/provider-auth-L08Tydtg.js';
const API_URL = 'https://token-plan-cn.xiaomimimo.com/v1/chat/completions';
const MODEL = 'mimo-v2.5-tts';
const VOICE_ID = '冰糖';

export function extractJsonObjects(text) {
  const objects = [];
  let start = -1;
  let depth = 0;
  let inString = false;
  let escaped = false;
  let lastEnd = 0;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (start < 0) {
      if (ch === '{') {
        start = i;
        depth = 1;
        inString = false;
        escaped = false;
      }
      continue;
    }
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        const raw = text.slice(start, i + 1);
        try {
          objects.push(JSON.parse(raw));
        } catch {
          // Keep the transport parser tolerant; the caller will fail if no audio arrives.
        }
        lastEnd = i + 1;
        start = -1;
      }
    }
  }

  const remainder = start >= 0 ? text.slice(start) : text.slice(lastEnd).replace(/^[\s\r\ndata:]+/i, '');
  return { objects, remainder };
}

export function audioFromPayload(payload) {
  const encoded = payload?.choices?.[0]?.message?.audio?.data;
  if (typeof encoded !== 'string' || !encoded) throw new Error('XIAOMI_TTS_AUDIO_INVALID');
  const audio = Buffer.from(encoded, 'base64');
  if (audio.length < 128) throw new Error('XIAOMI_TTS_AUDIO_INVALID');
  return audio;
}

async function writeBinary(buffer) {
  if (!process.stdout.write(buffer)) await once(process.stdout, 'drain');
}

async function resolveApiKey() {
  const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  const auth = await import(AUTH_MODULE);
  const apiKey = await auth.s({ cfg, provider: 'xiaomi-coding' });
  if (!apiKey) throw new Error('XIAOMI_TTS_AUTH_UNAVAILABLE');
  return apiKey;
}

async function streamSpeech(text) {
  if (!text.trim()) throw new Error('TTS_TEXT_REQUIRED');
  const apiKey = await resolveApiKey();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model: MODEL, messages: [{ role: 'assistant', content: text }], audio: { format: 'wav', voice: VOICE_ID } }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`XIAOMI_TTS_HTTP_${response.status}`);
    await writeBinary(audioFromPayload(await response.json()));
  } finally {
    clearTimeout(timeout);
  }
}

function selfTest() {
  const payload = { choices: [{ message: { audio: { data: Buffer.alloc(128, 7).toString('base64') } } }] };
  if (audioFromPayload(payload).length !== 128) throw new Error('audio decode');
  process.stderr.write('mimo_tts_stream self-test: PASS\n');
}

if (process.argv[1] && new URL(import.meta.url).pathname === process.argv[1]) {
  if (process.argv[2] === '--self-test') selfTest();
  else {
    const text = process.argv.slice(2).join(' ');
    streamSpeech(text).catch((error) => {
      process.stderr.write(`${error?.message || error}\n`);
      process.exitCode = 1;
    });
  }
}

#!/usr/bin/env node
import fs from 'node:fs';
import { once } from 'node:events';

const CONFIG_PATH = '/home/xyzlh/.openclaw/openclaw.json';
const AUTH_MODULE = 'file:///home/xyzlh/openclaw_workspace/node_modules/openclaw/dist/provider-auth-L08Tydtg.js';
const API_URL = 'https://api.minimaxi.com/v1/t2a_v2';
const MODEL = 'speech-2.8-turbo';
const VOICE_ID = 'Chinese (Mandarin)_Warm_Girl';

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
  const statusCode = payload?.base_resp?.status_code;
  if (Number.isFinite(statusCode) && statusCode !== 0) {
    throw new Error(`MINIMAX_TTS_STATUS_${statusCode}`);
  }
  if (payload?.event === 'task_failed') {
    throw new Error('MINIMAX_TTS_TASK_FAILED');
  }
  const hex = payload?.data?.audio;
  if (typeof hex !== 'string' || !hex.length) return null;
  if (hex.length % 2 !== 0 || !/^[0-9a-fA-F]+$/.test(hex)) {
    throw new Error('MINIMAX_TTS_AUDIO_INVALID');
  }
  const audio = Buffer.from(hex, 'hex');
  return audio.length ? audio : null;
}

async function writeBinary(buffer) {
  if (!process.stdout.write(buffer)) await once(process.stdout, 'drain');
}

async function resolveApiKey() {
  const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
  const auth = await import(AUTH_MODULE);
  const apiKey = await auth.s({ cfg, provider: 'minimax' });
  if (!apiKey) throw new Error('MINIMAX_AUTH_UNAVAILABLE');
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
      body: JSON.stringify({
        model: MODEL,
        text,
        stream: true,
        voice_setting: {
          voice_id: VOICE_ID,
          speed: 1,
          vol: 1,
          pitch: 0,
        },
        audio_setting: {
          sample_rate: 32000,
          bitrate: 128000,
          format: 'mp3',
          channel: 1,
        },
        subtitle_enable: false,
      }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) throw new Error(`MINIMAX_TTS_HTTP_${response.status}`);

    const decoder = new TextDecoder();
    let pending = '';
    let audioBytes = 0;
    for await (const chunk of response.body) {
      pending += decoder.decode(chunk, { stream: true });
      const parsed = extractJsonObjects(pending);
      pending = parsed.remainder;
      for (const payload of parsed.objects) {
        const audio = audioFromPayload(payload);
        if (audio) {
          audioBytes += audio.length;
          await writeBinary(audio);
        }
      }
    }
    pending += decoder.decode();
    const parsed = extractJsonObjects(pending);
    for (const payload of parsed.objects) {
      const audio = audioFromPayload(payload);
      if (audio) {
        audioBytes += audio.length;
        await writeBinary(audio);
      }
    }
    if (audioBytes < 128) throw new Error('MINIMAX_TTS_NO_AUDIO');
  } finally {
    clearTimeout(timeout);
  }
}

function selfTest() {
  const sample = 'data: {"data":{"audio":"49443304"},"base_resp":{"status_code":0}}\n' +
    '{"data":{"audio":"ffe31122"},"base_resp":{"status_code":0}}';
  const parsed = extractJsonObjects(sample);
  if (parsed.objects.length !== 2) throw new Error('parser count');
  const joined = Buffer.concat(parsed.objects.map(audioFromPayload).filter(Boolean));
  if (joined.toString('hex') !== '49443304ffe31122') throw new Error('audio decode');
  process.stderr.write('minimax_tts_stream self-test: PASS\n');
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

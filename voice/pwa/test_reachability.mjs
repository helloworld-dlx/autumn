import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const html = await readFile(new URL('./index.html', import.meta.url), 'utf8');
const worker = await readFile(new URL('./sw.js', import.meta.url), 'utf8');

test('service worker caches only the static Companion shell', () => {
  for (const asset of ['"/"', '"/index.html"', '"/continuous_voice.mjs"', '"/manifest.webmanifest"', '"/icons/autumn-192.png"', '"/icons/autumn-512.png"']) assert.match(worker, new RegExp(asset.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  for (const privateRoute of ['/api/', '/health', '/audio/', 'IndexedDB', 'sync']) assert.doesNotMatch(worker, new RegExp(privateRoute.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('connectivity is determined by same-origin health, not browser network state', () => {
  assert.match(html, /fetch\('\/health',\{cache:'no-store',signal:controller\.signal\}\)/);
  assert.match(html, /CONNECTING/);
  assert.match(html, /CONNECTED/);
  assert.match(html, /DISCONNECTED/);
  assert.doesNotMatch(html, /navigator\.onLine/);
});

test('Connect uses a fixed user-gesture Tailscale handoff and bounded return probes', () => {
  assert.match(html, /package=com\.tailscale\.ipn/);
  assert.match(html, /connectButton\.onclick=openTailscale/);
  assert.match(html, /for\(const delay of \[4000,10000\]\)/);
  assert.match(html, /visibilitychange/);
  assert.match(html, /pageshow/);
  assert.match(html, /window\.addEventListener\('focus'/);
});

test('Voice fails fast while Autumn is disconnected', () => {
  assert.match(html, /Autumn is disconnected\. Connect first\./);
  assert.match(html, /if\(connectivityState!==\'CONNECTED\'\)\{show\('连接'/);
  assert.match(html, /if\(connectivityState!==\'CONNECTED\'\)\{fail\('Autumn is disconnected\. Connect first\.'/);
});

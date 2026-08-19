const CACHE_NAME = "autumn-companion-shell-v21";
const APP_SHELL = [
  "/",
  "/index.html",
  "/continuous_voice.mjs",
  "/voice_entry.mjs",
  "/barge_in.mjs",
  "/eyes.mjs",
  "/spatial_shell.mjs",
  "/home_devices.mjs",
  "/nodes_ui.mjs",
  "/mobile_shell.mjs",
  "/manifest.webmanifest",
  "/icons/autumn-192.png",
  "/icons/autumn-512.png",
  "/assets/afterglow-home.webp",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys
        .filter((key) => key.startsWith("autumn-companion-shell-") && key !== CACHE_NAME)
        .map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !APP_SHELL.includes(url.pathname)) return;
  event.respondWith(
    fetch(event.request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)));
      }
      return response;
    }).catch(() => caches.match(event.request).then((cached) => cached || caches.match("/"))),
  );
});

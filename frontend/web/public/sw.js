// Minimal service worker: keeps the app installable on Android and
// always passes through to the network so dev servers and the local
// backend are never served stale content.
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  if (
    request.method !== "GET" ||
    !request.url.startsWith(self.location.origin)
  ) {
    return;
  }

  event.respondWith(fetch(request));
});

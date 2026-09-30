// Part 10: offline support. Network first; anything the site has shown before is kept,
// so a demo keeps working on bad venue Wi-Fi. Open each hero once before presenting.
const CACHE = 'sarabande-v1';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const response = await fetch(event.request);
      if (response.ok) cache.put(event.request, response.clone());
      return response;
    } catch (error) {
      const hit = await cache.match(event.request);
      if (hit) return hit;
      throw error;
    }
  })());
});

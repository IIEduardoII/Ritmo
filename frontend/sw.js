'use strict';
const CACHE = 'ritmo-shell-v1.1.1';
const SHELL = [
  '/', '/index.html', '/style.css', '/install.js', '/app.js',
  '/manifest.webmanifest', '/logo.svg', '/symbol.svg',
  '/icons/ritmo-192.png', '/icons/ritmo-512.png',
  '/icons/ritmo-maskable-512.png', '/icons/ritmo-apple-touch.png'
];
const SHELL_PATHS = new Set(SHELL);

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('ritmo-shell-') && key !== CACHE).map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (request.mode !== 'navigate' && !SHELL_PATHS.has(url.pathname)) return;
  event.respondWith((async () => {
    try {
      const response = await fetch(request);
      if (response.ok && SHELL_PATHS.has(url.pathname)) {
        const cache = await caches.open(CACHE);
        await cache.put(request, response.clone());
      }
      return response;
    } catch {
      return await caches.match(request) || (request.mode === 'navigate' ? caches.match('/index.html') : undefined)
        || new Response('Ritmo indisponível sem conexão.', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
    }
  })());
});

// Eventos de Web Push em segundo plano
self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : 'Treino agendado no Ritmo!' };
  }
  const title = data.title || 'Ritmo · Meus treinos';
  const options = {
    body: data.body || 'Você tem um treino agendado para agora.',
    icon: '/icons/ritmo-192.png',
    badge: '/icons/ritmo-192.png',
    tag: data.tag || 'ritmo-treino',
    renotify: true,
    data: { url: data.url || '/#inicio' }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/#inicio';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});

/* NEXUS Ledger service worker — Web Push + offline shell cache. */
const CACHE = "nexus-shell-v1";
const PRECACHE = ["/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("push", (event) => {
  let data = { title: "NEXUS", body: "New update", url: "/" };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (_err) {
    try {
      if (event.data) data.body = event.data.text();
    } catch (_err2) {
      /* keep defaults */
    }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "NEXUS", {
      body: data.body || "",
      data: { url: data.url || "/" },
      badge: "/static/icons/icon.svg",
      icon: "/static/icons/icon.svg",
      vibrate: [120, 60, 120],
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url && "focus" in client) {
          return client.focus().then((focused) => {
            if (focused && "navigate" in focused) return focused.navigate(target);
            return focused;
          });
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
      return undefined;
    })
  );
});

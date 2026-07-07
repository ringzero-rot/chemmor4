/* อาสาน้อย service worker — ออฟไลน์ + อัปเดต data.json สด */
const CACHE = "asanaoi-v1";
const SHELL = ["./", "./index.html", "./manifest.json",
               "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SHELL).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // data.json → network-first (สดเสมอ) แล้ว fallback แคช
  if (url.pathname.endsWith("data.json")) {
    e.respondWith(
      fetch(req).then((r) => {
        const copy = r.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req))
    );
    return;
  }

  // HTML / การนำทาง → network-first (เห็นเวอร์ชันใหม่ทันทีเมื่อออนไลน์) fallback แคชตอนออฟไลน์
  const isHTML = req.mode === "navigate" ||
                 (req.headers.get("accept") || "").includes("text/html") ||
                 url.pathname.endsWith(".html") || url.pathname.endsWith("/");
  if (isHTML) {
    e.respondWith(
      fetch(req).then((r) => {
        const copy = r.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return r;
      }).catch(() => caches.match(req).then((m) => m || caches.match("./index.html")))
    );
    return;
  }

  // อื่น ๆ (ไอคอน/ไฟล์คงที่) → cache-first
  e.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((r) => {
      if (r && r.status === 200 && url.origin === location.origin) {
        const copy = r.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return r;
    }).catch(() => cached))
  );
});

// แตะการแจ้งเตือน → เปิดแอป
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window" }).then((list) => {
      for (const c of list) { if ("focus" in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow("./");
    })
  );
});

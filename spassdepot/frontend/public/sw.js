// Minimaler Service Worker: ermöglicht Benachrichtigungen auf dem Handy
// (registration.showNotification) und bringt die App bei Antippen nach vorn.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window" }).then((fenster) => {
      if (fenster.length > 0) return fenster[0].focus();
      return self.clients.openWindow("/");
    }),
  );
});

self.addEventListener("install", event => {
  console.log("Service Worker installiert");
});

self.addEventListener("fetch", event => {
  // Optional: Offline-Verhalten
});

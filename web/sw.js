const CACHE_NAME="rakshak-ai-shell-v2";
const ASSETS=["/","/manifest.json","/static/styles.css","/static/app.js","/static/icons/icon-192.png","/static/icons/icon-512.png"];
self.addEventListener("install",e=>{e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(ASSETS)));self.skipWaiting();});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE_NAME).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener("fetch",e=>{const u=new URL(e.request.url);if(e.request.method!=="GET"||u.pathname.startsWith("/api/"))return;e.respondWith(fetch(e.request).then(r=>{const cp=r.clone();caches.open(CACHE_NAME).then(c=>c.put(e.request,cp));return r;}).catch(()=>caches.match(e.request)));});

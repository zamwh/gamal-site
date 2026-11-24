/* Lightweight, privacy-respecting analytics: anonymous ids, batched, never blocks the page. */
(function () {
  var S = null, V = null, isNew = 0, q = [], last = {}, timer = null;
  function rid(n) { var a = new Uint8Array(n || 12); (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach(function (_, i) { a[i] = Math.random() * 256 }); return Array.prototype.map.call(a, function (b) { return ('0' + b.toString(16)).slice(-2) }).join('') }
  try { S = sessionStorage.getItem('gm_s'); if (!S) { S = rid(10); sessionStorage.setItem('gm_s', S) } } catch (e) { S = rid(10) }
  try { V = localStorage.getItem('gm_v'); if (!V) { V = rid(10); isNew = 1; localStorage.setItem('gm_v', V) } } catch (e) { V = S; isNew = 1 }
  var online = location.protocol.indexOf('http') === 0;
  function flush(beacon) {
    if (!q.length || !online || window.GM_OFFLINE) { q = []; return }
    var body = JSON.stringify({ s: S, v: V, n: isNew, d: innerWidth < 760 ? 'mobile' : 'desktop', l: location.pathname.slice(0, 60), r: (document.referrer || '').split('/')[2] || '', e: q.splice(0, 40) });
    try {
      if (beacon && navigator.sendBeacon) navigator.sendBeacon('/api/ev', new Blob([body], { type: 'text/plain' }));
      else fetch('/api/ev', { method: 'POST', body: body, keepalive: true, headers: { 'Content-Type': 'text/plain' } }).catch(function () { });
    } catch (e) { }
  }
  window.T = function (type, code, value, viaAi) {
    try {
      var key = type + '|' + (code || '') + '|' + (value || ''), now = Date.now();
      if (last[key] && now - last[key] < 2500) return;          // de-duplicate rapid repeats
      last[key] = now;
      q.push({ id: rid(8), t: type, p: (location.pathname + location.hash).slice(0, 80), c: code || null, x: value ? String(value).slice(0, 60) : null, a: viaAi ? 1 : 0 });
      if (q.length >= 20) flush();
      clearTimeout(timer); timer = setTimeout(flush, 4000);
    } catch (e) { }
  };
  window.T.session = S; window.T.visitor = V;
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') flush(true) });
  addEventListener('pagehide', function () { flush(true) });
})();

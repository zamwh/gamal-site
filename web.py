# -*- coding: utf-8 -*-
"""Website server: customer site, piece pages (/p/CODE, also the QR target), assistant, analytics, requests.

Security: strict headers + CSP, per-IP rate limits, body-size limits, whitelisted static paths, receipts stored
outside any served folder, payment accounts revealed only after the terms are accepted (signed token).
"""
import base64
import hashlib
import hmac
import core
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core import GoldError
import admin

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(BASE, "site")
SITE = os.path.join(SITE_DIR, "index.html")
MAX_BODY = 20_000
MAX_UPLOAD = 4_500_000          # receipt image as base64 JSON
MAX_SYNC = 12_000_000           # a branch sending new pieces with their three photos
MAX_VOICE = 1_500_000           # one recorded sentence (up to ~25 s) as base64 JSON
STATIC = re.compile(r"/(img|fonts|js|css)/([A-Za-z0-9_.-]+\.(png|jpg|jpeg|webp|woff2|js|css|svg))")
CTYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "woff2": "font/woff2",
          "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "svg": "image/svg+xml"}
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; "
       "base-uri 'self'; form-action 'self'; object-src 'none'")
LIMITS = {"voice": (60, 60), "turn": (20, 60), "login": (6, 300), "chat": (12, 60), "terms": (10, 60), "request": (3, 600), "ev": (40, 60), "api": (90, 60), "static": (600, 60)}


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def media_dir(store, kind="media"):
    d = os.path.join(store.base_dir, kind, store.mode)
    os.makedirs(d, exist_ok=True)
    return d


class Server:
    def __init__(self, app, port=8080, host="0.0.0.0"):
        self.app = app
        self.port = port
        self.rate = {}
        self.rate_lock = threading.Lock()
        self.httpd = ThreadingHTTPServer((host, port), self._handler())
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()

    def url(self):
        return f"http://{lan_ip()}:{self.port}"

    def limited(self, ip, key):
        n, win = LIMITS[key]
        now = time.time()
        with self.rate_lock:
            b = [t for t in self.rate.get((ip, key), []) if now - t < win]
            b.append(now)
            self.rate[(ip, key)] = b
            if len(self.rate) > 20000:
                self.rate.clear()
        return len(b) > n

    # ---- signed token proving the terms were shown and accepted before accounts are revealed
    def _secret(self):
        return self.app.store.setting("secret").encode()

    def terms_token(self, code, kind):
        ts = str(int(time.time()))
        sig = hmac.new(self._secret(), f"{code}|{kind}|{ts}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"{ts}.{sig}"

    def check_token(self, tok, code, kind):
        try:
            ts, sig = tok.split(".")
            if time.time() - int(ts) > 6 * 3600:
                return False
            good = hmac.new(self._secret(), f"{code}|{kind}|{ts}".encode(), hashlib.sha256).hexdigest()[:32]
            return hmac.compare_digest(good, sig)
        except Exception:
            return False

    # ---- payloads
    def shops(self):
        """Where customers can come: only the shop on show (by its shop name), or every shop when all are shown."""
        s = self.app.store
        st, bid = core.storefront(s), core.online_branch(s)
        rows = s.branches()
        if bid:
            b = next((x for x in rows if x["id"] == bid), None) or {}
            return [{"n": st["name"], "addr": st["address"], "phone": b.get("phone"), "map": b.get("map_url"), "one": True}]
        return [{"n": b["name"], "addr": b["address"], "phone": b["phone"], "map": b["map_url"]} for b in rows]

    def site_payload(self):
        s = self.app.store
        bid = core.online_branch(s)
        pr = s.current_prices()
        prev = s.one("SELECT * FROM prices ORDER BY created_at DESC, rowid DESC LIMIT 1 OFFSET 1")
        prices = None
        if pr:
            ch = lambda k: (pr[k] - prev[k]) if prev and prev[k] else 0
            prices = {"k21": {"sell": pr["k21_sell"], "buy": pr["k21_buy"], "chg": ch("k21_sell")},
                      "pound": {"sell": pr["pound_sell"], "buy": pr["pound_buy"], "chg": ch("pound_sell")},
                      "updated": pr["created_at"], "rates": {"sar": pr["sar_rate"], "usd": pr["usd_rate"]}}
        hist = s.q("""SELECT substr(created_at,1,10) d, k21_sell v FROM prices WHERE rowid IN
                      (SELECT MAX(rowid) FROM prices GROUP BY substr(created_at,1,10)) ORDER BY d DESC LIMIT 30""")[::-1]
        res = s.setting("reservation")
        ai = self.app.agent.cfg()
        return {"v": 2, "demo": s.mode == "demo", "shop": s.setting("shop"), "prices": prices, "history": hist,
                "links": s.setting("links", {}), "deposit_pct": res["deposit_pct"],
                "branches": self.shops(),
                "pieces": [dict(self.app.agent._public(p, p["price"]), gallery=self.gallery(p))
                           for p in s.list_pieces(status="available") if core.online_ok(s, p, bid)],
                "policy": {"deposit": s.policy_text("deposit"), "full": s.policy_text("full")},
                "ai": bool(ai.get("enabled") and ai.get("api_key")),
                "hero": ["/media/" + n for n in (s.setting("hero", []) or []) if n][:3]}

    def gallery(self, p):
        """A piece's photos for the swipe strip inside its card: the card photo first, then the close-up and the original."""
        roles = core.piece_roles(p)
        first = core.card_photo(p)
        files = [first] + [roles[k] for k in core.PHOTO_ROLES if roles[k] and roles[k] != first] if first else []
        return [self.app.agent._murl(f) for f in dict.fromkeys(files)]

    def piece_payload(self, code):
        s = self.app.store
        p = s.piece(code)
        if not core.online_ok(s, p):
            return {"code": p["code"], "status": "hidden"}
        d = self.app.agent._public(p)
        roles = core.piece_roles(p)
        d.update({"photos": [self.app.agent._murl(f) for f in json.loads(p["photos"] or "[]")],
                  "gallery": [{"role": k, "url": self.app.agent._murl(roles[k])} for k in core.PHOTO_ROLES if roles[k]],
                  "description": p["description"], "occasion": p["occasion"],
                  "breakdown": s.piece_price(p), "price_time": (s.current_prices() or {}).get("created_at")})
        return d

    def _handler(self):
        server = self

        class H(BaseHTTPRequestHandler):
            server_version = "GM"
            sys_version = ""

            def log_message(self, *a):
                pass

            def _ip(self):
                return self.client_address[0]

            def _vip(self):     # behind the tunnel every visitor arrives from 127.0.0.1: use the address Cloudflare saw
                return (self.headers.get("Cf-Connecting-Ip") or self._ip())[:60]

            def _send(self, code, body, ctype="application/json; charset=utf-8", cache=None):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body, ensure_ascii=False).encode()
                elif isinstance(body, str):
                    body = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
                self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=(), payment=()")
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Content-Security-Policy", CSP)
                if self.headers.get("X-Forwarded-Proto") == "https":
                    self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                self.send_header("Cache-Control", cache or "no-store")
                if getattr(self, "_cookie", None):
                    self.send_header("Set-Cookie", self._cookie)
                    self._cookie = None
                try:
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    pass      # the page stopped loading (reload, closed): nothing to send to, not an error

            def _file(self, path, ctype, cache="public, max-age=86400"):
                if not os.path.isfile(path):
                    return self._send(404, {"error": "not found"})
                with open(path, "rb") as f:
                    return self._send(200, f.read(), ctype, cache)

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                uu = urllib.parse.urlparse(self.path)
                path, u_q = uu.path, uu.query
                app = server.app
                h = self.headers.get("Host", "")
                if h and not h.startswith(("127.", "localhost", "0.0.0.0")) and "." in h:
                    app.public_url = ("https://" if self.headers.get("X-Forwarded-Proto") == "https" or "trycloudflare" in h
                                      or h.split(":")[0].lower() in (app.store.setting("site_domains", []) or []) else "http://") + h
                    if app.public_url != getattr(app, "_pu_saved", None):     # the channel's buttons use the last real address
                        app._pu_saved = app.public_url
                        try:
                            import tg_channel
                            with app.lock:
                                if tg_channel.site_host_ok(app.store, h) and app.store.setting("public_url") != app.public_url:
                                    app.store.set_setting("public_url", app.public_url)
                        except Exception as e:
                            print("public_url:", e, flush=True)
                if path.startswith("/api/") and server.limited(self._ip(), "api"):
                    return self._send(429, {"error": "too many requests"})
                try:
                    if path == "/" or re.fullmatch(r"/p/[A-Za-z0-9]{1,20}", path):
                        with open(SITE, "rb") as f:
                            html = f.read().replace(b"<head>", b'<head><base href="/">', 1)
                        return self._send(200, html, "text/html; charset=utf-8", "no-cache")
                    m = STATIC.fullmatch(path)
                    if m and server.limited(self._ip(), "static"):
                        return self._send(429, {"error": "too many requests"})
                    if m:
                        return self._file(os.path.join(SITE_DIR, m.group(1), m.group(2)), CTYPES[m.group(3)])
                    m = re.fullmatch(r"/media/([A-Za-z0-9_-]+\.(jpg|jpeg|png|webp))", path)
                    if m:
                        with app.lock:
                            d = media_dir(app.store)
                        return self._file(os.path.join(d, m.group(1)), CTYPES[m.group(2)], "public, max-age=600")
                    if path in ("/pos", "/pos/", "/pos/index.html"):
                        # the shop program's own screen: only for the computer it runs on
                        if self.client_address[0] not in ("127.0.0.1", "::1"):
                            return self._send(404, {"error": "not found"})
                        with open(os.path.join(BASE, "ui", "index.html"), "rb") as f:
                            return self._send(200, f.read(), "text/html; charset=utf-8", "no-store")
                    m = re.fullmatch(r"/assets/((?:fonts/)?[A-Za-z0-9_.-]+\.(png|woff2|jpg))", path)
                    if m:
                        return self._file(os.path.join(BASE, "assets", m.group(1)), CTYPES[m.group(2)])
                    if path == "/scene":        # standalone cinematic scroll prototype
                        with open(os.path.join(SITE_DIR, "scene.html"), "rb") as f:
                            return self._send(200, f.read(), "text/html; charset=utf-8", "no-store")
                    if path in ("/admin", "/admin/"):
                        with open(os.path.join(SITE_DIR, "admin.html"), "rb") as f:
                            return self._send(200, f.read(), "text/html; charset=utf-8", "no-store")
                    if path.startswith("/api/admin/"):
                        u = admin.user_for(app, self.headers.get("Cookie"))
                        if not u:
                            return self._send(401, {"error": "سجّل الدخول"})
                        m = re.fullmatch(r"/api/admin/receipt/([A-Za-z0-9_.]+)", path)
                        if m:
                            fp = admin.receipt_path(app, m.group(1))
                            if not fp:
                                return self._send(404, {"error": "not found"})
                            return self._file(fp, CTYPES[fp.rsplit(".", 1)[1]], "private, no-store")
                        q = {k: v[0] for k, v in urllib.parse.parse_qs(u_q).items()}
                        return self._send(200, admin.get(app, u, path, q))
                    if path == "/api/voice/status":     # may this visitor talk to the voice salesman now?
                        v = getattr(app, "voice", None)
                        if not v:
                            return self._send(200, {"on": False})
                        vq = {k: x[0] for k, x in urllib.parse.parse_qs(u_q).items()}
                        staff = bool(admin.user_for(app, self.headers.get("Cookie")))
                        return self._send(200, v.status(str(vq.get("v", ""))[:40], self._vip(), staff))
                    if path == "/api/wa/webhook":     # Meta checks the WhatsApp webhook address once
                        wa = getattr(app, "wa", None)
                        ch = wa.verify_get(urllib.parse.parse_qs(u_q)) if wa else None
                        if ch is None:
                            return self._send(403, {"error": "forbidden"})
                        return self._send(200, ch.encode(), "text/plain; charset=utf-8", "no-cache")
                    if path == "/api/site":
                        with app.lock:
                            return self._send(200, server.site_payload())
                    if path == "/api/eval/trace":   # evaluation sessions only: what the model asked the backend, step by step
                        sess = (urllib.parse.parse_qs(u_q).get("session") or [""])[0]
                        if not sess.startswith("evaltest"):
                            return self._send(404, {"error": "not found"})
                        with app.lock:
                            return self._send(200, {"rows": app.store.q("SELECT turn, tool, args, result FROM ai_trace WHERE session=? ORDER BY id", (sess,))})
                    if path == "/api/avail":      # live stock: what the page may still offer right now
                        with app.lock:
                            bid = core.online_branch(app.store)
                            rows = app.store.q("SELECT code, status FROM pieces WHERE show_online=1 AND status IN ('available','reserved')"
                                               + (" AND branch_id=?" if bid else ""), (bid,) if bid else ())
                            v = app.store.one("SELECT COALESCE(MAX(updated_at),'') AS v, COUNT(*) AS n FROM pieces")
                        return self._send(200, {"v": f"{v['v']}|{v['n']}", "available": [r["code"] for r in rows if r["status"] == "available"],
                                                "reserved": [r["code"] for r in rows if r["status"] == "reserved"]})
                    m = re.fullmatch(r"/api/piece/([A-Za-z0-9]{1,20})", path)
                    if m:
                        with app.lock:
                            return self._send(200, server.piece_payload(m.group(1)))
                    return self._send(404, {"error": "not found"})
                except GoldError as e:
                    return self._send(404, {"error": str(e)})
                except Exception:
                    import traceback; traceback.print_exc()     # never hide an error: it goes to the server log
                    return self._send(500, {"error": "server error"})

            def do_POST(self):
                path = urllib.parse.urlparse(self.path).path
                ip = self._ip()
                limit = (MAX_SYNC if path == "/api/pos/sync" else
                         MAX_UPLOAD if path in ("/api/request", "/api/admin/photo") else
                         MAX_VOICE if path == "/api/voice/turn" else MAX_BODY)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = 0
                if n <= 0 or n > limit:
                    return self._send(413, {"error": "حجم الطلب غير مسموح"})
                origin = self.headers.get("Origin")
                host = self.headers.get("Host", "")
                if origin and urllib.parse.urlparse(origin).netloc != host:
                    return self._send(403, {"error": "forbidden"})
                if path == "/api/wa/webhook":         # Meta: WhatsApp messages (signed with the app secret, raw body)
                    wa = getattr(server.app, "wa", None)
                    raw = self.rfile.read(n)
                    if not wa:
                        return self._send(404, {"error": "not found"})
                    try:
                        code = wa.webhook(raw, self.headers.get("X-Hub-Signature-256", ""))
                    except Exception:
                        import traceback; traceback.print_exc()
                        code = 500
                    return self._send(code, {"ok": code == 200})
                if path == "/api/phone/webhook":      # OpenAI: a call reached the shop's project (signed, raw body)
                    ph = getattr(server.app, "phone", None)
                    raw = self.rfile.read(n)
                    if not ph:
                        return self._send(404, {"error": "not found"})
                    try:
                        code, out = ph.webhook(raw, {k.lower(): v for k, v in self.headers.items()})
                    except Exception:
                        import traceback; traceback.print_exc()
                        code, out = 500, {"error": "server error"}
                    return self._send(code, out)
                try:
                    data = json.loads(self.rfile.read(n).decode() or "{}")
                    if not isinstance(data, dict):
                        raise ValueError
                except ValueError:
                    return self._send(400, {"error": "bad json"})
                app = server.app
                try:
                    if path == "/api/admin/login":
                        if server.limited(ip, "login"):
                            return self._send(429, {"error": "محاولات كثيرة، انتظر 5 دقائق"})
                        tok, u = admin.login(app, str(data.get("username", "")), str(data.get("password", "")))
                        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                        self._cookie = f"gm_admin={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={admin.TTL}{secure}"
                        return self._send(200, {"name": u["name"], "role": u["role"]})
                    if path == "/api/admin/logout":
                        admin.logout(self.headers.get("Cookie"))
                        self._cookie = "gm_admin=; Max-Age=0; Path=/"
                        return self._send(200, {"ok": True})
                    if path.startswith("/api/admin/"):
                        u = admin.user_for(app, self.headers.get("Cookie"))
                        if not u:
                            return self._send(401, {"error": "سجّل الدخول"})
                        return self._send(200, admin.post(app, u, path, data))
                    if path == "/api/ev":
                        if server.limited(ip, "ev"):
                            return self._send(204, b"")
                        if app.analytics:
                            app.analytics.ingest(data)
                        return self._send(204, b"")
                    if path == "/api/pos/sync":       # branch POS: queued offline sales in, live stock and price out
                        if server.limited(ip, "api"):
                            return self._send(429, {"error": "too many requests"})
                        import pos_sync
                        with app.lock:
                            res = pos_sync.sync(app.store, data)
                        if app.analytics and res.get("stock"):     # who looked at each piece / saved it, shown next to it in the shop program
                            try:
                                res["interest"] = app.analytics.piece_interest([x["code"] for x in res["stock"]])
                            except Exception as e:
                                print("interest:", e, flush=True)
                        return self._send(200, res)
                    if path.startswith("/api/voice/"):   # the voice salesman: open / delegate / beat / close
                        v = getattr(app, "voice", None)
                        if not v:
                            return self._send(404, {"error": "not found"})
                        if server.limited(self._vip(), "voice"):
                            return self._send(429, {"ok": False, "why": "rate"})
                        call = str(data.get("call", ""))[:20]
                        if path == "/api/voice/open":
                            staff = bool(admin.user_for(app, self.headers.get("Cookie")))
                            return self._send(200, v.open(str(data.get("visitor", ""))[:40], str(data.get("session", "")),
                                                          str(data.get("sdp", "")), self._vip(), staff, bool(data.get("resume")),
                                                          str(data.get("voice", ""))[:20] or None))
                        if path == "/api/voice/turn":      # «رد ورد» voices: one recorded sentence in, the answer and its audio out
                            if server.limited(self._vip(), "turn"):
                                return self._send(429, {"ok": False, "why": "rate"})
                            staff = bool(admin.user_for(app, self.headers.get("Cookie")))
                            picks = data.get("picks") if isinstance(data.get("picks"), list) else None
                            ms = data.get("ms")
                            return self._send(200, v.turn(str(data.get("visitor", ""))[:40], str(data.get("session", "")),
                                                          str(data.get("audio", "")), str(data.get("mime", ""))[:60],
                                                          ms if isinstance(ms, (int, float)) else 0, self._vip(), staff, picks,
                                                          bool(data.get("hello")), str(data.get("voice", ""))[:20] or None))
                        if path == "/api/voice/delegate":
                            picks = data.get("picks") if isinstance(data.get("picks"), list) else None
                            return self._send(200, v.delegate(call, str(data.get("text", "")), picks))
                        if path == "/api/voice/beat":
                            sbm = data.get("standby_ms")
                            return self._send(200, v.beat(call, sbm if isinstance(sbm, (int, float)) else None))
                        if path == "/api/voice/close":
                            usage = data.get("usage") if isinstance(data.get("usage"), (dict, list)) else None
                            sbm = data.get("standby_ms")
                            return self._send(200, v.close(call, usage, str(data.get("reason", "end"))[:20],
                                                           sbm if isinstance(sbm, (int, float)) else None))
                        return self._send(404, {"error": "not found"})
                    if path == "/api/chat":
                        if server.limited(ip, "chat"):
                            return self._send(429, {"error": "رسائل كثيرة، انتظر دقيقة"})
                        picks = data.get("picks") if isinstance(data.get("picks"), list) else None   # his shortlist, from his browser
                        return self._send(200, app.agent.chat(str(data.get("session", "")), str(data.get("message", "")), str(data.get("visitor", "") or ""), picks))
                    if path == "/api/terms":
                        if server.limited(ip, "terms"):
                            return self._send(429, {"error": "محاولات كثيرة"})
                        code, kind = str(data.get("code", "")).upper()[:20], str(data.get("kind", ""))
                        if kind not in ("deposit", "full") or not data.get("accepted"):
                            return self._send(400, {"error": "لازم توافق على الشروط"})
                        with app.lock:
                            p = app.store.piece(code)
                            if p["status"] != "available" or not core.online_ok(app.store, p):
                                raise GoldError("القطعة غير متاحة حالياً")
                            price = app.store.piece_price(p)["total"]
                            pct = float(app.store.setting("reservation")["deposit_pct"])
                            amount = price if kind == "full" else round(price * pct / 100)
                            accounts = app.store.setting("payments", []) or []
                        return self._send(200, {"token": server.terms_token(code, kind), "accounts": accounts,
                                                "amount": amount, "price": price})
                    if path == "/api/request":
                        if server.limited(ip, "request"):
                            return self._send(429, {"error": "طلبات كثيرة، حاول بعد قليل"})
                        code, kind = str(data.get("code", "")).upper()[:20], str(data.get("kind", ""))
                        if not server.check_token(str(data.get("token", "")), code, kind):
                            return self._send(400, {"error": "اعرض الشروط ووافق عليها أولاً"})
                        raw = str(data.get("receipt", ""))
                        mm = re.match(r"data:image/(jpeg|jpg|png|webp);base64,(.+)$", raw, re.S)
                        if not mm:
                            return self._send(400, {"error": "أرفق صورة الإيصال (JPG أو PNG)"})
                        blob = base64.b64decode(mm.group(2), validate=False)
                        if len(blob) > 3_300_000 or not (blob[:3] == b"\xff\xd8\xff" or blob[:8] == b"\x89PNG\r\n\x1a\n"
                                                          or blob[8:12] == b"WEBP"):
                            return self._send(400, {"error": "الصورة غير صالحة أو كبيرة"})
                        with app.lock:
                            d = media_dir(app.store, "receipts")      # never served over HTTP
                            name = f"{int(time.time())}_{secrets.token_hex(6)}.{'png' if blob[:4] == b'\x89PNG' else 'jpg'}"
                            with open(os.path.join(d, name), "wb") as f:
                                f.write(blob)
                            r = app.store.request_reservation(code, str(data.get("name", "")), str(data.get("phone", "")),
                                                              True, kind, str(data.get("payer", "")), name, "web",
                                                              str(data.get("session", "")), str(data.get("pickup", "")))
                        return self._send(200, r)
                    return self._send(404, {"error": "not found"})
                except GoldError as e:
                    return self._send(400, {"error": str(e)})
                except Exception:
                    import traceback; traceback.print_exc()     # never hide an error: it goes to the server log
                    return self._send(500, {"error": "server error"})

        return H

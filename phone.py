"""Phone calls to the shop's premium customers (prototype, started by the owner from the admin).

How a call works
- The server asks OpenAI to place the call itself (GPT-Live over SIP): POST /v1/live/sessions with a SIP transport that
  goes out through the shop's Zadarma line (its SIP login and password, entered by the owner in the admin, never in
  the code). OpenAI rings the customer; the call shows the shop's caller number.
- A small listener on the server attaches to the call («sideband») to follow it: ringing, answered, the words both
  ways, the end. It keeps the call short: at 1:30 it tells the advisor to close politely, and at 1:58 it hangs up
  itself (the line bills by the minute, so a third minute is never started). No answer within 45 s: it hangs up.
- The advisor speaks Gulf Arabic, greets the customer by name, tells him gold went down, and offers to send the newest
  collections on WhatsApp. Today's gram price is written into its instructions from the shop's own price, never guessed.
- After the call the owner gets a Telegram note: who, how long, what the customer said (so the team sends the WhatsApp).
"""
import base64
import hashlib
import hmac
import datetime as dt
import json
import math
import os
import re
import secrets
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

LIVE_URL = "https://api.openai.com/v1/live/sessions"
ZD_API = "https://api.zadarma.com"
WS_BASE = "wss://api.openai.com/v1/live/sessions"

DEFAULT = {
    "enabled": True,
    "sip_user": "",               # the Zadarma SIP login (e.g. 454051)
    "sip_pass": "",               # its password: kept on the server only
    "caller": "",                 # the number the customer sees (Zadarma's confirmed caller number), e.g. +966...
    "provider_url": "sips:sip.zadarma.com:5061",
    "voice": "coral",             # the owner picks it in the admin; female voices: coral, marin, shimmer
    "model": "gpt-live-1",
    "wrap_s": 90,                 # answered this long -> the advisor is told to close
    "max_s": 118,                 # answered this long -> the server hangs up (the line bills whole minutes)
    "ring_s": 45,                 # no answer in this long -> hang up
    "per_day": 25,                # calls the server will place in a day
    "oai_per_min": 0.05,          # OpenAI's voice price
    "line_per_min": 0.144,        # Zadarma Economy, Yemen mobile, whole minutes
    # the second way («callback»): Zadarma rings the customer itself and hands the call to the advisor
    "zd_key": "", "zd_secret": "",  # Zadarma API key and secret (Settings -> Integrations and API)
    "pbx_ext": "100",             # the Zadarma PBX extension that forwards to OpenAI's SIP address
    "wh_secret": "",              # OpenAI's webhook secret (whsec_...), to trust only OpenAI's notices
    "proj_id": "",                # the OpenAI project id (proj_...), shown to build the SIP address
    "zd_sip": "",                 # the Zadarma line the customer's leg goes out from (empty: the SIP login above)
    "predicted": False,           # True: Zadarma rings the customer first (did not run on a trial account, 27 Nov)
    "cb_wrap_s": 105,             # callback: from OpenAI's pickup (customer still ringing) to the wrap-up
    "cb_max_s": 135,              # ... to the hang-up
}

SCRIPT = """أنت «المستشار الآلي لمجوهرات جمال المشرقي»، تتصل بالهاتف على عميل مميز من عملاء المحل.
المحل واحد: «جمال المشرقي للذهب والمجوهرات»، بجوار البوابة الرئيسية لمركز جرعان، إب. لا تقول «فرع» أبداً.
اللهجة: خليجية بس، جمل قصيرة ودافية ومحترمة.
الصوت: تكلم بصوت عالي وواضح، كأنك تكلم في جوال والطرف الثاني لازم يسمعك زين، بدون صراخ وبدون همس. لا تستخدم كلمات شامية ولا مصرية (ولا «إيه» ولا «كده» ولا «بدك»).
النبرة: تكلم مثل إنسان طبيعي مبتسم، مو مثل إعلان ولا مثل واحد يقرأ ورقة. غيّر نبرتك حسب الموقف:
- لو العميل مزح أو ضحك: اضحك ضحكة خفيفة طبيعية ورد عليه بروح حلوة.
- وأنت تبلغه بنزول الذهب: بحماس وفرحة خفيفة، كأنك تبشره بخبر حلو.
- لو قال إنه مشغول أو تعبان: هدّي صوتك وكن لطيف ومختصر.
- لو رحب فيك بحرارة: رد الترحيب بحرارة.
خذ نفس طبيعي بين الجمل، ونوّع في سرعتك، ولا تسرد الكلام سرد.

النطق الصحيح (انطق هذي الكلمات كذا بالضبط):
- المَشْرِقي (الميم مفتوحة، والشين ساكنة، والراء مكسورة)
- جَرْعان (الجيم مفتوحة، والراء ساكنة)
- إِبّ (الهمزة مكسورة، والباء مشددة)
- مُجَوْهَرات
- تَشْكِيلات
- حَصْرِيّة
- عِيار واحِد وعِشْرين
- اسم العميل: انطقه مثل ما ينطقه اليمنيين، ولو سمعته منه بنطق ثاني امشِ على نطقه هو.
- الأرقام والأسعار: قلها بالكلمات العربية واضحة، مثل «ثلاثمية وخمسين ألف ريال».

اسم العميل: {name}
الخبر: {news}
سعر بيع جرام الذهب عيار 21 اليوم عند المحل: {gram}. قله بس لو سأل عن السعر، وبالرقم هذا بالضبط.
المحل يفتح يومياً من 9 الصبح إلى 10 بالليل.

ترتيب المكالمة (المكالمة كلها أقل من دقيقتين). التحية والتعريف قلها مثل ما هي، والباقي خذ الفكرة وقلها بكلامك الطبيعي:
1. أول ما يرد: «السلام عليكم، كيف الحال أستاذ {name}؟ إن شاء الله تكون بخير وعافية.» واسكت واسمع رده.
2. لو رد بالحمد أو سألك عن حالك: «الحمد لله، بخير.» ثم: «معك المستشار الآلي لمجوهرات جمال المشرقي.»
3. الخبر: «{news_line}»
4. العرض: «وعندنا تشكيلات جديدة حصرية، أتوقع بعضها يناسب ذوقك. تحب أرسلها لك على الواتساب وتطّلع عليها على راحتك؟»
5. لو وافق: «أبشر، أرسلها لك على طول بعد المكالمة.» ثم الختام.
   لو اعتذر أو مشغول: «ولا يهمك، نتشرف فيك في أي وقت.» ثم الختام.
   لو طلب خصم أو حجز أو تفاصيل كثيرة: «فريق المبيعات يكمل معك على الواتساب بالتفصيل.» ثم الختام.
6. الختام: «شكراً على وقتك أستاذ {name}، والله يحفظك. مع السلامة.»

قواعد:
- لا تعدد قطع ولا أسعار قطع في المكالمة؛ كل التفاصيل على الواتساب.
- لا تعطي وعد بخصم، ولا تذكر المصنعية، ولا تسأل عن أحد من أهل العميل.
- لو العميل تكلم وأنت تتكلم، اسكت واسمعه.
- لو قال إنه ما يبغى اتصالات: اعتذر بلطف وقل إنك بتبلغ الفريق، ثم الختام.
- لا تطول: لو قربت الدقيقة ونص، روح للختام مباشرة."""

NEWS = {"normal": ("الذهب صار فيه نزول اليوم",
                   "حبيت أبلغك إن الذهب صار فيه نزول، ولأنك من عملائنا المميزين حبينا نبلغك قبل الكل."),
        "strong": ("الذهب نزل نزول قوي اليوم",
                   "حبيت أبلغك إن الذهب نزل اليوم نزول واضح، ولأنك من عملائنا المميزين حبينا نبلغك قبل الكل، عشان ما تفوتك الفرصة.")}
WRAP = "الوقت قرب يخلص: روح للختام الحين بجملة وحدة مهذبة، وقل مع السلامة."


def norm_phone(p):
    """A Yemeni or Saudi number as the customer gives it -> +967... / +966..."""
    s = re.sub(r"[^\d+]", "", p or "")
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        return s if 9 <= len(s) <= 16 else ""
    if re.fullmatch(r"7\d{8}", s):                 # Yemeni mobile without the country code
        return "+967" + s
    if re.fullmatch(r"05\d{8}", s):                # Saudi mobile
        return "+966" + s[1:]
    if re.fullmatch(r"(967|966)\d{8,9}", s):
        return "+" + s
    return ""


class WS:
    """The smallest websocket client the sideband needs (text frames, ping/pong, close); no outside library."""
    def __init__(self, url, headers, timeout=15):
        u = urllib.parse.urlparse(url)
        host, port = u.hostname, u.port or (443 if u.scheme == "wss" else 80)
        raw = socket.create_connection((host, port), timeout)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if u.scheme == "wss" else raw
        key = base64.b64encode(os.urandom(16)).decode()
        req = ["GET %s HTTP/1.1" % ((u.path or "/") + (("?" + u.query) if u.query else "")), "Host: %s" % host,
               "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Key: " + key, "Sec-WebSocket-Version: 13"]
        req += ["%s: %s" % kv for kv in headers.items()]
        self.s.sendall(("\r\n".join(req) + "\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.s.recv(4096)
            if not chunk:
                raise ConnectionError("closed during handshake")
            head += chunk
        head, self.buf = head.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode("latin-1")[:120])

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self, op, data):
        hdr = bytes([0x80 | op])
        n = len(data)
        hdr += bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + n.to_bytes(2, "big") if n < 65536 else bytes([0x80 | 127]) + n.to_bytes(8, "big"))
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send(self, obj):
        self._frame(1, json.dumps(obj, ensure_ascii=False).encode())

    def recv(self, timeout=1.0):
        """One text message, None on timeout; raises ConnectionError when closed."""
        self.s.settimeout(timeout)
        msg, first = b"", True
        while True:
            try:
                b1, b2 = self._read(2)
            except socket.timeout:
                if first:
                    return None
                raise ConnectionError("cut")
            first = False
            self.s.settimeout(10)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = int.from_bytes(self._read(2), "big")
            elif n == 127:
                n = int.from_bytes(self._read(8), "big")
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if op == 8:
                raise ConnectionError("closed by server")
            if op == 9:
                self._frame(10, data)
                continue
            if op in (1, 0, 2):
                msg += data
                if b1 & 0x80:
                    return msg.decode("utf-8", "ignore")

    def close(self):
        try:
            self._frame(8, b"")
        except Exception:
            pass
        try:
            self.s.close()
        except Exception:
            pass


class Phone:
    def __init__(self, app):
        self.app, self.store, self.agent = app, app.store, app.agent
        self.lock = threading.Lock()
        with app.lock:
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS phone_calls (
                id TEXT PRIMARY KEY, session_id TEXT, name TEXT, phone TEXT, kind TEXT, by_user TEXT, day TEXT,
                created REAL, answered REAL, ended REAL, status TEXT, reason TEXT, talk_s REAL DEFAULT 0,
                cost REAL DEFAULT 0, transcript TEXT, usage TEXT)""")
            self.store.db.commit()

    def cfg(self):
        c = dict(DEFAULT)
        try:
            c.update({k: v for k, v in (self.store.setting("phone", {}) or {}).items() if k in DEFAULT})
        except Exception:
            pass
        return c

    def mode(self, c=None):
        c = c or self.cfg()
        return "callback" if (c["zd_key"] and c["zd_secret"] and c["wh_secret"]) else "direct"

    def ready(self):
        c = self.cfg()
        if not c["enabled"]:
            return False
        if self.mode(c) == "callback":
            return bool(c["pbx_ext"])
        return bool(c["sip_user"] and c["sip_pass"] and norm_phone(c["caller"]))

    def _female(self, voice):
        return voice in ("coral", "marin", "shimmer", "sage", "nova", "alloy")

    def _gendered(self, instr, voice):
        """A female voice speaks of herself as a woman (the customer is still «أستاذ»)."""
        if not self._female(voice):
            return instr
        for a, b in (("أنت «المستشار الآلي لمجوهرات جمال المشرقي»، تتصل", "أنتِ «المستشارة الآلية لمجوهرات جمال المشرقي»، تتصلين"),
                     ("«الحمد لله، بخير.» ثم: «معك المستشار الآلي لمجوهرات جمال المشرقي.»", "«الحمد لله، بخير.» ثم: «معك المستشارة الآلية لمجوهرات جمال المشرقي.»"),
                     ("«أبشر، أرسلها لك", "«أبشر، أرسلها لك"), ("تكلم بصوت عالي", "تكلمي بصوت عالي"), ("كأنك تكلم في جوال", "كأنك تكلمين في جوال")):
            instr = instr.replace(a, b)
        return instr + "\nأنتِ امرأة: تكلمي عن نفسك بصيغة المؤنث (أنا معك، أنا جاهزة)."

    def _gram(self):
        try:
            p = self.store.current_prices()
            return "{:,.0f} ريال".format(float(p["k21_sell"])) if p and p["k21_sell"] else "غير مسجل، قل له إن الفريق يرسله على الواتساب"
        except Exception:
            return "غير مسجل، قل له إن الفريق يرسله على الواتساب"

    def _update(self, cid, **kw):
        with self.app.lock:
            self.store.db.execute("UPDATE phone_calls SET " + ", ".join(k + "=?" for k in kw) + " WHERE id=?",
                                  list(kw.values()) + [cid])
            self.store.db.commit()

    # ---- place a call (the owner, from the admin)
    def call(self, name, phone, kind, by_user="owner"):
        c, key = self.cfg(), self.agent.cfg().get("api_key")
        name = re.sub(r"[^\w\s؀-ۿ.-]", "", name or "").strip()[:40]
        dest = norm_phone(phone)
        kind = "strong" if kind == "strong" else "normal"
        if not self.ready():
            return {"ok": False, "why": "أدخل بيانات Zadarma في الإعدادات"}
        if not key:
            return {"ok": False, "why": "مفتاح OpenAI غير موجود"}
        if not name or not dest:
            return {"ok": False, "why": "اكتب اسم العميل ورقم جوال يمني صحيح"}
        if not dest.startswith("+967"):            # Zadarma's line to other countries answered with recordings (27 Nov)
            return {"ok": False, "why": "المكالمات لأرقام اليمن بس (طريق Zadarma لباقي الدول يرد بتسجيلات ويحسب دقائق)"}
        today = dt.date.today().isoformat()
        n = self.store.one("SELECT COUNT(*) n FROM phone_calls WHERE day=?", (today,))["n"]
        if n >= int(c["per_day"]):
            return {"ok": False, "why": "وصلت حد المكالمات اليومي (%d)" % int(c["per_day"])}
        news, line = NEWS[kind]
        instr = self._gendered(SCRIPT.format(name=name, news=news, news_line=line, gram=self._gram()), c["voice"])
        if self.mode(c) == "callback":
            return self._callback(c, name, dest, kind, by_user, today, instr)
        body = {"session": {"model": c["model"], "instructions": instr, "audio": {"output": {"voice": c["voice"]}}},
                "transport": {"type": "sip", "destination": dest,
                              "trunk": {"provider_url": c["provider_url"],
                                        "auth": {"type": "digest", "username": str(c["sip_user"]), "password": str(c["sip_pass"])},
                                        "caller_number": norm_phone(c["caller"])}}}
        req = urllib.request.Request(LIVE_URL, json.dumps(body, ensure_ascii=False).encode(),
                                     {"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode() or "{}")
            except Exception:
                err = {}
            msg = str((err.get("error") or {}).get("message") or "")[:200]
            code = str((err.get("error") or {}).get("code") or "")
            why = ("OpenAI ما فعّل الاتصال الصادر لحسابك بعد" if "outbound_sip_not_enabled" in (code + msg)
                   else "OpenAI رفض المكالمة")
            return {"ok": False, "why": why, "detail": ("%s %s %s" % (e.code, code, msg)).strip()}
        except Exception as e:
            return {"ok": False, "why": "ما قدرنا نوصل لـOpenAI", "detail": str(e)[:200]}
        sid = (d.get("session") or {}).get("id")
        if not sid:
            return {"ok": False, "why": "OpenAI ما رجّع رقم المكالمة", "detail": json.dumps(d)[:200]}
        cid = secrets.token_hex(6)
        with self.app.lock:
            self.store.db.execute("INSERT INTO phone_calls (id,session_id,name,phone,kind,by_user,day,created,status) "
                                  "VALUES (?,?,?,?,?,?,?,?,?)", (cid, sid, name, dest, kind, by_user, today, time.time(), "dialing"))
            self.store.db.commit()
        threading.Thread(target=self._watch, args=(cid, sid, key, c), daemon=True).start()
        return {"ok": True, "id": cid}

    # ---- the second way: Zadarma rings the customer, its PBX extension hands the call to OpenAI
    def _zd(self, method, params, c):
        """A Zadarma API call, signed the way its official library signs (HMAC-SHA1 of method + query + md5(query))."""
        q = urllib.parse.urlencode(sorted(params.items()))
        sig = base64.b64encode(hmac.new(c["zd_secret"].encode(), (method + q + hashlib.md5(q.encode()).hexdigest()).encode(),
                                        hashlib.sha1).hexdigest().encode()).decode()
        req = urllib.request.Request(ZD_API + method + ("?" + q if q else ""), headers={"Authorization": c["zd_key"] + ":" + sig})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode() or "{}")
            except Exception:
                return {"status": "error", "message": "HTTP %s" % e.code}
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}

    def _callback(self, c, name, dest, kind, by_user, today, instr):
        cid = secrets.token_hex(6)
        with self.app.lock:
            self.store.db.execute("INSERT INTO phone_calls (id,session_id,name,phone,kind,by_user,day,created,status,usage) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?)", (cid, None, name, dest, kind, by_user, today, time.time(), "dialing",
                                                                   json.dumps({"instructions": instr}, ensure_ascii=False)))
            self.store.db.commit()
        params = {"from": str(c["pbx_ext"]), "to": dest}          # Zadarma support: international format with "+"
        # Zadarma: with a PBX extension in "from", the line in "sip" must be a PBX extension too. Extension 100
        # forwards to OpenAI (it cannot dial out itself), so the customer's leg goes out from extension 101.
        ext = str(c["pbx_ext"])
        line = str(c.get("zd_sip") or ("101" if ext.isdigit() and len(ext) <= 4 and ext != "101" else c.get("sip_user")) or "").strip()
        if line:
            params["sip"] = line                   # the customer's leg goes out from the line that can call Yemen
        if c.get("predicted"):
            params["predicted"] = "1"              # ring the customer first; the advisor joins when he answers
        d = self._zd("/v1/request/callback/", params, c)
        if d.get("status") != "success":
            msg = str(d.get("message") or d)[:200]
            self._update(cid, status="failed", reason="Zadarma: " + msg, ended=time.time())
            return {"ok": False, "why": "Zadarma رفض الاتصال", "detail": msg}
        return {"ok": True, "id": cid, "mode": "callback"}

    def _verify(self, raw, headers, secret):
        """OpenAI's webhook signature (Standard Webhooks): HMAC-SHA256 over id.timestamp.body with the whsec_ secret."""
        wid, ts, sigs = headers.get("webhook-id") or "", headers.get("webhook-timestamp") or "", headers.get("webhook-signature") or ""
        if not (wid and ts and sigs and secret):
            return False
        try:
            if abs(time.time() - int(ts)) > 600:
                return False
            key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
        except Exception:
            return False
        good = base64.b64encode(hmac.new(key, ("%s.%s." % (wid, ts)).encode() + raw, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(good, part.split(",", 1)[1]) for part in sigs.split() if "," in part)

    def webhook(self, raw, headers):
        """OpenAI tells us a call reached the shop's project: if we asked Zadarma for it a moment ago, the advisor takes it."""
        c, key = self.cfg(), self.agent.cfg().get("api_key")
        if not self._verify(raw, headers, c["wh_secret"]):
            return 401, {"error": "bad signature"}
        try:
            ev = json.loads(raw.decode() or "{}")
        except ValueError:
            return 400, {"error": "bad json"}
        if ev.get("type") not in ("live.transport.incoming", "live.call.incoming"):
            return 200, {"ok": True}
        data = ev.get("data") or {}
        sid = data.get("session_id") or data.get("call_id")
        if not sid:
            return 200, {"ok": True}
        with self.lock:
            row = self.store.one("SELECT * FROM phone_calls WHERE status='dialing' AND session_id IS NULL AND created>? "
                                 "ORDER BY created DESC LIMIT 1", (time.time() - 90,))
            if row:
                self._update(row["id"], session_id=sid, status="ringing")
        if not row:                                # nobody asked for this call: refuse it
            self._post(LIVE_URL + "/%s/reject" % sid, {"status_code": 486}, key)
            return 200, {"ok": True}
        try:
            instr = json.loads(row["usage"] or "{}").get("instructions") or ""
        except ValueError:
            instr = ""
        if c.get("predicted"):
            instr += "\n\nمهم: العميل رد على جواله الحين. ابدأ بالسلام مباشرة."
        else:
            instr += ("\n\nمهم: أنت تدخل المكالمة قبل ما العميل يرد. اسكت تماماً وانتظر لين تسمع صوت العميل (مثل «ألو» أو «نعم»)، "
                      "وبعدها ابدأ بالسلام.")
        code = self._post(LIVE_URL + "/%s/accept" % sid, {"session": {"type": "live", "model": c["model"], "instructions": instr,
                                                                       "audio": {"output": {"voice": c["voice"]}}}}, key)
        if code != 200:
            self._update(row["id"], status="failed", reason="OpenAI accept: %s" % code, ended=time.time())
            return 200, {"ok": True}
        cc = c if c.get("predicted") else dict(c, wrap_s=c["cb_wrap_s"], max_s=c["cb_max_s"])
        self._update(row["id"], usage=None)
        threading.Thread(target=self._watch, args=(row["id"], sid, key, cc, True), daemon=True).start()
        return 200, {"ok": True}

    def _post(self, url, body, key):
        req = urllib.request.Request(url, json.dumps(body, ensure_ascii=False).encode(), {"Authorization": "Bearer " + (key or ""),
                                                                                         "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                r.read()
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0

    def _hangup(self, sid, key):
        req = urllib.request.Request(LIVE_URL + "/%s/hangup" % sid, b"", {"Authorization": "Bearer " + key}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=15).read()
            return True
        except Exception:
            return False

    def _watch(self, cid, sid, key, c, inbound=False):
        """Follow the call on the sideband: ringing, answered, words, the end; close it on time."""
        t0, answered, wrapped, hung, lines, usage, status, reason = time.time(), None, False, False, [], None, "dialing", ""
        if inbound:                                # the advisor picked up (the customer's phone rings from now)
            answered, status = t0, "answered"
            self._update(cid, status=status, answered=answered)
        cur = {"u": "", "a": ""}
        ws = None
        try:
            ws = WS(WS_BASE + "/%s/attach" % sid, {"Authorization": "Bearer " + key})
            while True:
                now = time.time()
                if not hung and answered is None and now - t0 > float(c["ring_s"]):
                    hung = self._hangup(sid, key) or True; reason = reason or "no_answer"
                if answered and not wrapped and now - answered >= float(c["wrap_s"]):
                    wrapped = True
                    try:
                        ws.send({"type": "session.instructions.append", "event_id": "wrap" + secrets.token_hex(3), "content": WRAP})
                    except Exception:
                        pass
                if answered and not hung and now - answered >= float(c["max_s"]):
                    hung = self._hangup(sid, key) or True; reason = reason or "time"
                if now - t0 > float(c["ring_s"]) + float(c["max_s"]) + 60:
                    if not hung:
                        self._hangup(sid, key)
                    reason = reason or "stuck"
                    break
                raw = ws.recv(0.5)
                if raw is None:
                    continue
                try:
                    m = json.loads(raw)
                except ValueError:
                    continue
                t = m.get("type", "")
                if t == "transport.ringing" and status == "dialing":
                    status = "ringing"; self._update(cid, status=status)
                elif t == "transport.answered":
                    answered = time.time(); status = "answered"; self._update(cid, status=status, answered=answered)
                elif t == "transport.failed":
                    status = "failed"; reason = str(m.get("reason") or (m.get("error") or {}).get("message") or "failed")[:120]
                elif t.endswith("input_transcript.delta"):
                    if cur["a"]:
                        lines.append("المستشار: " + cur["a"].strip()); cur["a"] = ""
                    cur["u"] += m.get("delta") or ""
                elif t.endswith("output_transcript.delta"):
                    if cur["u"]:
                        lines.append("العميل: " + cur["u"].strip()); cur["u"] = ""
                    cur["a"] += m.get("delta") or ""
                elif t == "session.closed":
                    usage = m.get("usage") or (m.get("message") or {}).get("usage")
                    break
        except Exception as e:
            reason = reason or ("sideband: " + str(e)[:100])
            if not hung:
                time.sleep(2)
                if answered is None:
                    pass
        finally:
            if ws:
                ws.close()
        if cur["u"].strip():
            lines.append("العميل: " + cur["u"].strip())
        if cur["a"].strip():
            lines.append("المستشار: " + cur["a"].strip())
        end = time.time()
        talk = max(0.0, end - answered) if answered else 0.0
        line_min = math.ceil(talk / 60.0) if talk > 0.5 else 0
        cost = round(line_min * float(c["line_per_min"]) + (end - t0) / 60.0 * float(c["oai_per_min"]), 4)
        final = "done" if answered else (status if status == "failed" else "no_answer")
        self._update(cid, status=final, reason=reason, ended=end, talk_s=round(talk, 1), cost=cost,
                     transcript="\n".join(lines)[:4000], usage=json.dumps(usage, ensure_ascii=False)[:1500] if usage else None)
        an = getattr(self.agent, "analytics", None)
        if an:
            try:
                an.log_ai("phone-" + cid, c["model"], "voice", "phone", "phone:" + final, 0, 0, 0,
                          round((end - t0) / 60.0 * float(c["oai_per_min"]), 5), int((end - t0) * 1000), "")
            except Exception:
                pass
        row = self.store.one("SELECT * FROM phone_calls WHERE id=?", (cid,))
        self._card(row, final, talk, cost, reason, lines)

    def _card(self, row, final, talk, cost, reason, lines):
        """The owner's Telegram card: who, how it went, whether he agreed; the words behind a button."""
        said = " ".join(x for x in lines if x.startswith("المستشار"))
        heard = " ".join(x for x in lines if x.startswith("العميل"))
        if final != "done":
            res = {"no_answer": "ما رد", "failed": "ما اتصلت"}.get(final, final)
        elif "أبشر" in said or "أرسلها لك على طول" in said:
            res = "وافق يستقبل التشكيلات على الواتساب ✅"
        elif any(w in heard for w in ("لا شكرا", "لا شكراً", "مشغول", "ما ابغى", "ما أبغى", "مو الحين")):
            res = "اعتذر"
        else:
            res = "تمت المكالمة (افتح التفاصيل)"
        card = "📞 مكالمة عميل مميز\n%s · %s\n%s\n%d:%02d · حوالي %.0f سنت" % (row["name"], row["phone"], res, int(talk) // 60, int(talk) % 60, cost * 100)
        if reason and final != "done":
            card += "\nالسبب: " + reason[:120]
        bot = getattr(self.app, "bot", None)
        try:
            if bot and hasattr(bot, "notify_card") and lines:
                bot.notify_card(card, [{"text": "تفاصيل المكالمة", "callback_data": "pc:" + row["id"]}])
            else:
                fn = getattr(self.agent, "notify", None)
                if fn:
                    fn(card)
        except Exception:
            pass

    # ---- the owner's view
    def recent(self, n=20):
        # a Zadarma call that never reached the advisor (the customer did not answer, or OpenAI's notice never came)
        stale = self.store.q("SELECT id FROM phone_calls WHERE status='dialing' AND session_id IS NULL AND created<?", (time.time() - 120,))
        for r in stale:
            self._update(r["id"], status="no_answer", ended=time.time(),
                         reason="ما وصل المستشار: العميل ما رد، أو Zadarma ما حوّل المكالمة، أو إشعار OpenAI ما وصل")
        rows = self.store.q("SELECT * FROM phone_calls ORDER BY created DESC LIMIT ?", (n,))
        out = []
        for r in rows:
            out.append({"id": r["id"], "when": dt.datetime.fromtimestamp(r["created"]).strftime("%m-%d %H:%M"), "name": r["name"],
                        "phone": r["phone"], "kind": r["kind"], "status": r["status"], "reason": r["reason"] or "",
                        "talk_s": r["talk_s"] or 0, "cost": r["cost"] or 0, "transcript": r["transcript"] or ""})
        c = self.cfg()
        today = dt.date.today().isoformat()
        return {"calls": out, "ready": self.ready(), "today": self.store.one("SELECT COUNT(*) n FROM phone_calls WHERE day=?", (today,))["n"],
                "per_day": c["per_day"], "month_cost": round(float(self.store.one(
                    "SELECT COALESCE(SUM(cost),0) c FROM phone_calls WHERE day>=?", (dt.date.today().replace(day=1).isoformat(),))["c"] or 0), 3)}

    def settings_view(self):
        c = self.cfg()
        m = lambda v: ("••••" + v[-4:]) if v else ""
        return {"sip_user": c["sip_user"], "has_pass": bool(c["sip_pass"]), "sip_pass": ("••••" + c["sip_pass"][-2:]) if c["sip_pass"] else "",
                "caller": c["caller"], "enabled": c["enabled"] is not False, "mode": self.mode(c),
                "zd_key": m(c["zd_key"]), "zd_secret": m(c["zd_secret"]), "wh_secret": m(c["wh_secret"]),
                "pbx_ext": c["pbx_ext"], "proj_id": c["proj_id"], "voice": c["voice"],
                "sip_uri": ("sip:%s@sip.api.openai.com;transport=tls" % c["proj_id"]) if c["proj_id"] else ""}

    def save(self, d):
        cur = dict(self.store.setting("phone", {}) or {})
        if "sip_user" in d:
            cur["sip_user"] = re.sub(r"[^\w.@-]", "", str(d["sip_user"]))[:40]
        pw = str(d.get("sip_pass") or "").strip()
        if pw and not pw.startswith("••••"):
            cur["sip_pass"] = pw[:80]
        if "caller" in d:
            cur["caller"] = norm_phone(str(d["caller"])) or ""
        if "enabled" in d:
            cur["enabled"] = bool(d["enabled"])
        for k in ("zd_key", "zd_secret", "wh_secret"):
            v = str(d.get(k) or "").strip()
            if v and not v.startswith("••••"):
                cur[k] = v[:200]
        if str(d.get("voice") or "") in ("coral", "marin", "shimmer", "echo", "ballad", "ash", "cedar"):
            cur["voice"] = str(d["voice"])
        if "pbx_ext" in d:
            cur["pbx_ext"] = re.sub(r"[^\w-]", "", str(d["pbx_ext"]))[:20]
        if "proj_id" in d:
            cur["proj_id"] = re.sub(r"[^\w-]", "", str(d["proj_id"]))[:60]
        self.store.set_setting("phone", cur)

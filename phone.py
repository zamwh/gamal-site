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
WS_BASE = "wss://api.openai.com/v1/live/sessions"

DEFAULT = {
    "enabled": True,
    "sip_user": "",               # the Zadarma SIP login (e.g. 454051)
    "sip_pass": "",               # its password: kept on the server only
    "caller": "",                 # the number the customer sees (Zadarma's confirmed caller number), e.g. +966...
    "provider_url": "sips:sip.zadarma.com:5061",
    "voice": "echo",
    "model": "gpt-live-1",
    "wrap_s": 90,                 # answered this long -> the advisor is told to close
    "max_s": 118,                 # answered this long -> the server hangs up (the line bills whole minutes)
    "ring_s": 45,                 # no answer in this long -> hang up
    "per_day": 25,                # calls the server will place in a day
    "oai_per_min": 0.05,          # OpenAI's voice price
    "line_per_min": 0.144,        # Zadarma Economy, Yemen mobile, whole minutes
}

SCRIPT = """أنت «المستشار الآلي لمجوهرات جمال المشرقي»، تتصل بالهاتف على عميل مميز من عملاء المحل.
المحل واحد: «جمال المشرقي للذهب والمجوهرات»، بجوار البوابة الرئيسية لمركز جرعان، إب. لا تقول «فرع» أبداً.
اللهجة: خليجية بس، جمل قصيرة ودافية ومحترمة. لا تستخدم كلمات شامية ولا مصرية (ولا «إيه» ولا «كده» ولا «بدك»).

اسم العميل: {name}
الخبر: {news}
سعر بيع جرام الذهب عيار 21 اليوم عند المحل: {gram}. قله بس لو سأل عن السعر، وبالرقم هذا بالضبط.
المحل يفتح يومياً من 9 الصبح إلى 10 بالليل.

ترتيب المكالمة (المكالمة كلها أقل من دقيقتين):
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

    def ready(self):
        c = self.cfg()
        return bool(c["enabled"] and c["sip_user"] and c["sip_pass"] and norm_phone(c["caller"]))

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
            return {"ok": False, "why": "أدخل بيانات خط Zadarma (الدخول وكلمة السر ورقم المتصل) في الإعدادات"}
        if not key:
            return {"ok": False, "why": "مفتاح OpenAI غير موجود"}
        if not name or not dest:
            return {"ok": False, "why": "اكتب اسم العميل ورقم جوال صحيح (يمني أو سعودي)"}
        today = dt.date.today().isoformat()
        n = self.store.one("SELECT COUNT(*) n FROM phone_calls WHERE day=?", (today,))["n"]
        if n >= int(c["per_day"]):
            return {"ok": False, "why": "وصلت حد المكالمات اليومي (%d)" % int(c["per_day"])}
        news, line = NEWS[kind]
        instr = SCRIPT.format(name=name, news=news, news_line=line, gram=self._gram())
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

    def _hangup(self, sid, key):
        req = urllib.request.Request(LIVE_URL + "/%s/hangup" % sid, b"", {"Authorization": "Bearer " + key}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=15).read()
            return True
        except Exception:
            return False

    def _watch(self, cid, sid, key, c):
        """Follow the call on the sideband: ringing, answered, words, the end; close it on time."""
        t0, answered, wrapped, hung, lines, usage, status, reason = time.time(), None, False, False, [], None, "dialing", ""
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
        st = {"done": "تمت المكالمة", "no_answer": "ما رد", "failed": "ما اتصلت"}.get(final, final)
        note = "📞 مكالمة عميل مميز: %s (%s)\n%s · %d ثانية · حوالي %.0f سنت" % (row["name"], row["phone"], st, int(talk), cost * 100)
        if reason and final != "done":
            note += "\nالسبب: " + reason
        if lines:
            note += "\n\n" + "\n".join(lines)[:1500] + "\n\nلو وافق: أرسلوا له التشكيلات على الواتساب."
        try:
            fn = getattr(self.agent, "notify", None)
            if fn:
                fn(note)
        except Exception:
            pass

    # ---- the owner's view
    def recent(self, n=20):
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
        return {"sip_user": c["sip_user"], "has_pass": bool(c["sip_pass"]), "sip_pass": ("••••" + c["sip_pass"][-2:]) if c["sip_pass"] else "",
                "caller": c["caller"], "enabled": c["enabled"] is not False}

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
        self.store.set_setting("phone", cur)

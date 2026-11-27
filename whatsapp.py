# -*- coding: utf-8 -*-
"""WhatsApp for the shop (Meta's official WhatsApp Cloud API), ready before it is linked.

Switched on by the owner only: Admin > Settings > «واتساب» (or Telegram «⚙️ التحكم» > «💬 الواتساب») once Meta's
values are typed there. Nothing secret is in the code: the token and app secret live in the shop database.

What it does
- Customers write to the shop's WhatsApp -> the same sales agent as the website answers (text, then up to 3 pieces
  as photo + caption + link). One answer at a time per customer, a daily cap per customer, the agent's own spending cap.
- Coexistence (the shop keeps its number on the WhatsApp Business app): when a person from the shop answers a customer
  from the phone, Meta sends an "echo" (field smb_message_echoes). The agent then stays quiet with that customer for
  `human_quiet_min` minutes, so the shop and the agent never talk over each other.
- After a phone call where the customer agreed, the owner presses «📲 أرسل له العروض على الواتساب» on the Telegram card
  (or it goes by itself when `auto_after_call` is on): an approved template message (a business-started message must
  be a template) with the customer's name and the site link.
- The owner can stop the agent on WhatsApp at any moment; messages are still recorded and reach Telegram.

Meta's side (done once, by the owner, see docs/SYSTEM_GUIDE.txt):
  webhook URL  = <public address>/api/wa/webhook   verify token = shown in the admin
  subscribe the app to the fields: messages (and smb_message_echoes with coexistence)
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request

GRAPH = "https://graph.facebook.com/{v}/{path}"

DEFAULT = {
    "enabled": False,             # the agent answers customers on WhatsApp (off until the owner switches it on)
    "phone_number_id": "",        # Meta: WhatsApp > API setup > Phone number ID
    "waba_id": "",                # Meta: WhatsApp Business Account ID (for reference)
    "token": "",                  # Meta: a permanent System User access token (kept on the server only)
    "app_secret": "",             # Meta: App settings > Basic > App secret (to trust only Meta's webhook calls)
    "verify_token": "",           # made by the server; typed by the owner in Meta's webhook settings
    "graph_version": "v23.0",
    "per_customer_day": 40,       # agent answers to one customer in a day
    "human_quiet_min": 30,        # a person from the shop answered from the phone -> the agent waits this long
    "template_offer": "",         # the approved template sent after a call (e.g. "gold_offer"); {{1}} = the name
    "template_lang": "ar",
    "auto_after_call": False,     # send the template by itself when the call card says the customer agreed
    "notify_staff": True,         # a short notice on Telegram for every new customer conversation
}

WELCOME_OFF = ("أهلاً وسهلاً بك في جمال المشرقي للذهب والمجوهرات. وصلت رسالتك، وفريق المبيعات يرد عليك في أقرب وقت. "
               "الدوام يومياً من 9 الصبح إلى 10 بالليل.")


def norm_wa(p):
    """Meta's wa_id (digits, country code first) -> +967..."""
    d = re.sub(r"\D", "", p or "")
    return "+" + d if d else ""


class WhatsApp:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.lock = threading.Lock()
        self.busy = set()            # customers whose answer is being written (one at a time each)
        self.seen = {}               # Meta message id -> time (Meta may deliver the same message twice)
        with app.lock:
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS wa_messages (
                id TEXT PRIMARY KEY, wa TEXT, dir TEXT, kind TEXT, body TEXT, ts REAL, status TEXT, by TEXT)""")
            self.store.db.execute("CREATE INDEX IF NOT EXISTS wa_messages_wa ON wa_messages (wa, ts)")
            c = dict(self.store.setting("whatsapp", {}) or {})
            if not c.get("verify_token"):
                c["verify_token"] = secrets.token_hex(12)
                self.store.set_setting("whatsapp", c)
            self.store.db.commit()

    # ---------- settings
    def cfg(self):
        c = dict(DEFAULT)
        c.update({k: v for k, v in (self.store.setting("whatsapp", {}) or {}).items() if k in DEFAULT})
        return c

    def ready(self, c=None):
        c = c or self.cfg()
        return bool(c["phone_number_id"] and c["token"])

    def save(self, d):
        with self.app.lock:
            c = dict(self.store.setting("whatsapp", {}) or {})
            for k in DEFAULT:
                if k not in d or k == "verify_token":
                    continue
                v = d[k]
                if k in ("token", "app_secret") and (not v or "•" in str(v)):
                    continue                       # masked value sent back unchanged: keep the stored one
                if isinstance(DEFAULT[k], bool):
                    v = bool(v)
                elif isinstance(DEFAULT[k], int):
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        continue
                else:
                    v = str(v).strip()[:400]
                c[k] = v
            self.store.set_setting("whatsapp", c)
            self.store.db.commit()
        return self.settings_view()

    def settings_view(self):
        c = self.cfg()
        mask = lambda s: ("•" * 8 + s[-4:]) if s else ""
        base = (getattr(self.app, "public_url", "") or "").rstrip("/")
        return {"enabled": c["enabled"], "phone_number_id": c["phone_number_id"], "waba_id": c["waba_id"],
                "token": mask(c["token"]), "app_secret": mask(c["app_secret"]), "verify_token": c["verify_token"],
                "graph_version": c["graph_version"], "per_customer_day": c["per_customer_day"],
                "human_quiet_min": c["human_quiet_min"], "template_offer": c["template_offer"],
                "template_lang": c["template_lang"], "auto_after_call": c["auto_after_call"],
                "notify_staff": c["notify_staff"], "ready": self.ready(c),
                "webhook_url": (base + "/api/wa/webhook") if base else "/api/wa/webhook"}

    # ---------- Meta's webhook
    def verify_get(self, q):
        """GET /api/wa/webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=... -> the challenge, or None."""
        c = self.cfg()
        g = lambda k: (q.get(k) or [""])[0]
        if g("hub.mode") == "subscribe" and c["verify_token"] and hmac.compare_digest(g("hub.verify_token"), c["verify_token"]):
            return g("hub.challenge")[:200]
        return None

    def _signed(self, raw, header):
        c = self.cfg()
        if not c["app_secret"]:
            return False                          # no secret typed yet: trust nothing
        want = "sha256=" + hmac.new(c["app_secret"].encode(), raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, (header or "").strip())

    def webhook(self, raw, sig_header):
        """POST from Meta. Always quick: the answers are written in the background."""
        if not self._signed(raw, sig_header):
            return 401
        try:
            d = json.loads(raw.decode("utf-8"))
        except Exception:
            return 400
        for e in d.get("entry") or []:
            for ch in e.get("changes") or []:
                v = ch.get("value") or {}
                field = ch.get("field")
                if field == "smb_message_echoes":            # the shop answered from the WhatsApp Business app
                    for m in v.get("message_echoes") or []:
                        self._log(m.get("id") or secrets.token_hex(8), norm_wa(m.get("to")), "out", m.get("type", "text"),
                                  ((m.get("text") or {}).get("body") or "")[:1000], "sent", "staff")
                    continue
                if field != "messages":
                    continue
                for m in v.get("messages") or []:
                    mid = m.get("id") or ""
                    with self.lock:
                        if mid in self.seen:
                            continue
                        self.seen[mid] = time.time()
                        if len(self.seen) > 2000:
                            for k in sorted(self.seen, key=self.seen.get)[:1000]:
                                self.seen.pop(k, None)
                    name = ((v.get("contacts") or [{}])[0].get("profile") or {}).get("name", "")
                    threading.Thread(target=self._on_message, args=(m, name), daemon=True).start()
                for st in v.get("statuses") or []:
                    with self.app.lock:
                        self.store.db.execute("UPDATE wa_messages SET status=? WHERE id=?", (st.get("status"), st.get("id")))
                        self.store.db.commit()
        return 200

    # ---------- answering
    def _text_of(self, m):
        t = m.get("type")
        if t == "text":
            return (m.get("text") or {}).get("body", "")
        if t == "button":
            return (m.get("button") or {}).get("text", "")
        if t == "interactive":
            i = m.get("interactive") or {}
            return (i.get("button_reply") or i.get("list_reply") or {}).get("title", "")
        return ""

    def _on_message(self, m, name):
        wa = norm_wa(m.get("from"))
        text = self._text_of(m).strip()
        kind = m.get("type", "text")
        self._log(m.get("id") or secrets.token_hex(8), wa, "in", kind, text[:1000] or "[" + kind + "]", "received", name[:40])
        c = self.cfg()
        first = self._count(wa, "in", 86400 * 30) <= 1
        if c["notify_staff"] and first:
            self._notify(f"💬 زبون جديد على الواتساب: {name or ''} {wa}\n«{text[:120]}»")
        if not c["enabled"] or not self.ready(c):
            if first and self.ready(c):
                self.send_text(wa, WELCOME_OFF, by="auto")
            return
        if self._human_recent(wa, c):
            return                                 # someone from the shop is talking with him
        if not text:
            return self.send_text(wa, "وصلتني رسالتك. اكتب لي طلبك كتابة، مثل نوع القطعة أو الميزانية، وأخدمك على طول.", by="agent")
        if self._count(wa, "out", 86400, by="agent") >= int(c["per_customer_day"]):
            return
        with self.lock:
            if wa in self.busy:
                return
            self.busy.add(wa)
        try:
            r = self.app.agent.chat("wa" + re.sub(r"\D", "", wa)[-12:], text, "wa" + re.sub(r"\D", "", wa)[-12:])
            reply = re.sub(r"\[\[[A-Za-z0-9]+\]\]", "", r.get("text") or "")
            reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
            if reply:
                self.send_text(wa, reply, by="agent")
            for p in (r.get("pieces") or [])[:3]:
                self._send_piece(wa, p)
        except Exception as e:
            print("whatsapp answer:", e, flush=True)
        finally:
            with self.lock:
                self.busy.discard(wa)

    def _send_piece(self, wa, p):
        base = (getattr(self.app, "public_url", "") or "").rstrip("/")
        link = f"{base}/p/{p['code']}" if base else ""
        price = p.get("price")
        cap = (f"{p.get('title') or p.get('kind')}\nالوزن {p.get('weight')} جم · عيار {p.get('karat')}"
               + (f"\nالسعر بسعر اليوم: {float(price):,.0f} ريال" if price else "") + (f"\n{link}" if link else ""))
        if base and p.get("photo"):
            return self._api({"messaging_product": "whatsapp", "to": re.sub(r"\D", "", wa), "type": "image",
                              "image": {"link": base + p["photo"], "caption": cap[:1000]}}, wa, "image", cap, "agent")
        return self.send_text(wa, cap, by="agent")

    # ---------- sending
    def send_text(self, wa, text, by="agent"):
        return self._api({"messaging_product": "whatsapp", "to": re.sub(r"\D", "", wa), "type": "text",
                          "text": {"body": text[:4000], "preview_url": True}}, wa, "text", text, by)

    def send_template(self, wa, name, params=None, by="owner"):
        c = self.cfg()
        tpl = (name or c["template_offer"] or "").strip()
        if not tpl:
            return {"ok": False, "why": "اكتب اسم قالب العروض المعتمد في إعدادات الواتساب"}
        comp = [{"type": "body", "parameters": [{"type": "text", "text": str(x)[:60]} for x in (params or [])]}] if params else []
        body = {"messaging_product": "whatsapp", "to": re.sub(r"\D", "", wa), "type": "template",
                "template": {"name": tpl, "language": {"code": c["template_lang"] or "ar"}, "components": comp}}
        return self._api(body, wa, "template", tpl + " " + " ".join(map(str, params or [])), by)

    def offer_after_call(self, name, phone, by="owner"):
        """The customer agreed on the call: the approved offers template, {{1}} = his name."""
        c = self.cfg()
        if not self.ready(c):
            return {"ok": False, "why": "الواتساب للحين ما انربط"}
        return self.send_template(phone, c["template_offer"], [name or "عميلنا"], by=by)

    def _api(self, body, wa, kind, text, by):
        c = self.cfg()
        if not self.ready(c):
            return {"ok": False, "why": "الواتساب للحين ما انربط"}
        url = GRAPH.format(v=c["graph_version"] or "v23.0", path=c["phone_number_id"] + "/messages")
        req = urllib.request.Request(url, json.dumps(body, ensure_ascii=False).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + c["token"]})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode()).get("error", {})
                why = f"{err.get('code', e.code)}: {err.get('message', '')}"[:200]
            except Exception:
                why = str(e.code)
            self._log(secrets.token_hex(8), wa, "out", kind, (text or "")[:1000], "failed: " + why, by)
            return {"ok": False, "why": why}
        except Exception as e:
            self._log(secrets.token_hex(8), wa, "out", kind, (text or "")[:1000], "failed: " + str(e)[:150], by)
            return {"ok": False, "why": str(e)[:150]}
        mid = ((d.get("messages") or [{}])[0]).get("id") or secrets.token_hex(8)
        self._log(mid, wa, "out", kind, (text or "")[:1000], "sent", by)
        return {"ok": True, "id": mid}

    # ---------- records
    def _log(self, mid, wa, dr, kind, body, status, by):
        with self.app.lock:
            self.store.db.execute("INSERT OR REPLACE INTO wa_messages (id,wa,dir,kind,body,ts,status,by) VALUES (?,?,?,?,?,?,?,?)",
                                  (mid, wa, dr, kind, body, time.time(), status, by))
            self.store.db.commit()

    def _count(self, wa, dr, within, by=None):
        with self.app.lock:
            q = "SELECT COUNT(*) n FROM wa_messages WHERE wa=? AND dir=? AND ts>?" + (" AND by=?" if by else "")
            return self.store.one(q, (wa, dr, time.time() - within) + ((by,) if by else ()))["n"]

    def _human_recent(self, wa, c):
        with self.app.lock:
            r = self.store.one("SELECT MAX(ts) t FROM wa_messages WHERE wa=? AND dir='out' AND by='staff'", (wa,))
        return bool(r and r["t"] and time.time() - r["t"] < int(c["human_quiet_min"]) * 60)

    def _notify(self, text):
        bot = getattr(self.app, "bot", None)
        try:
            if bot:
                bot.notify(text)
        except Exception:
            pass

    def stats(self):
        day = time.time() - 86400
        with self.app.lock:
            g = lambda q, a=(): self.store.one(q, a)["n"]
            return {"in_today": g("SELECT COUNT(*) n FROM wa_messages WHERE dir='in' AND ts>?", (day,)),
                    "out_today": g("SELECT COUNT(*) n FROM wa_messages WHERE dir='out' AND ts>?", (day,)),
                    "customers_today": g("SELECT COUNT(DISTINCT wa) n FROM wa_messages WHERE dir='in' AND ts>?", (day,)),
                    "failed_today": g("SELECT COUNT(*) n FROM wa_messages WHERE status LIKE 'failed%' AND ts>?", (day,))}

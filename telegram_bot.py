"""Telegram channel: customers talk to the same sales brain as the website; linked staff talk to the internal agent.
Long-polling with the standard library only. Settings live in the shop database (setting "telegram")."""
import json, mimetypes, os, random, threading, time, urllib.error, urllib.parse, urllib.request, uuid

API = "https://api.telegram.org/bot{}/{}"


def cfg(store):
    c = store.setting("telegram", {}) or {}
    if not c.get("link_code"):
        c["link_code"] = f"{random.randint(100000, 999999)}"
        store.set_setting("telegram", c)
        store.db.commit()
    c.setdefault("staff", {})
    return c


class Bot(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self.offset = 0
        self.mode = {}          # staff chat id -> "staff" | "customer"
        self.status = "stopped"
        self.username = ""

    # ---------- telegram calls
    def call(self, token, method, data=None, timeout=35):
        req = urllib.request.Request(API.format(token, method), json.dumps(data or {}).encode(),
                                     {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

    def send(self, token, chat, text, buttons=None):
        d = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}
        if buttons:
            d["reply_markup"] = {"inline_keyboard": [[b] for b in buttons]}
        try:
            self.call(token, "sendMessage", d)
        except Exception as e:
            print("telegram send:", e, flush=True)

    def send_photo(self, token, chat, path, caption, buttons=None):
        bnd = uuid.uuid4().hex
        fields = {"chat_id": str(chat), "caption": caption[:1000]}
        if buttons:
            fields["reply_markup"] = json.dumps({"inline_keyboard": [[b] for b in buttons]}, ensure_ascii=False)
        body = b""
        for k, v in fields.items():
            body += f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        body += (f"--{bnd}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{os.path.basename(path)}\"\r\n"
                 f"Content-Type: {mimetypes.guess_type(path)[0] or 'image/jpeg'}\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{bnd}--\r\n".encode()
        req = urllib.request.Request(API.format(token, "sendPhoto"), body, {"Content-Type": f"multipart/form-data; boundary={bnd}"})
        try:
            urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:
            print("telegram photo:", e, flush=True)
            self.send(token, chat, caption, buttons)

    def notify(self, text):
        """Owner/staff notices (sales, reservations, restock). Sent in the background, never blocks a sale."""
        def go():
            try:
                with self.app.lock:
                    c = cfg(self.app.store)
                token = (c.get("token") or "").strip()
                if not token or not c.get("enabled", True):
                    return
                for chat in list((c.get("staff") or {}).keys()):
                    if chat not in (c.get("muted") or []):
                        self.send(token, chat, text)
            except Exception as e:
                print("telegram notify:", e, flush=True)
        threading.Thread(target=go, daemon=True).start()

    # ---------- loop
    def run(self):
        while True:
            try:
                with self.app.lock:
                    c = cfg(self.app.store)
                token = (c.get("token") or "").strip()
                if not token or not c.get("enabled", True):
                    self.status = "stopped"
                    time.sleep(20)
                    continue
                if not self.username:
                    me = self.call(token, "getMe")
                    self.username = me["result"].get("username", "")
                self.status = "running"
                r = self.call(token, "getUpdates", {"offset": self.offset, "timeout": 25,
                                                    "allowed_updates": ["message", "callback_query"]}, timeout=40)
                for u in r.get("result", []):
                    self.offset = u["update_id"] + 1
                    try:
                        self.handle(token, u)
                    except Exception as e:
                        print("telegram handle:", e, flush=True)
            except urllib.error.HTTPError as e:
                self.status = f"error {e.code}"
                self.username = ""
                time.sleep(30)
            except Exception as e:
                self.status = "offline"
                time.sleep(10)

    def handle(self, token, u):
        if u.get("callback_query"):
            q = u["callback_query"]
            self.call(token, "answerCallbackQuery", {"callback_query_id": q["id"]})
            msg = {"chat": q["message"]["chat"], "from": q["from"], "text": q.get("data", "")}
        else:
            msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat, uid = msg.get("chat", {}).get("id"), str(msg.get("from", {}).get("id", ""))
        if not chat or not text:
            return
        app = self.app
        with app.lock:
            c = cfg(app.store)
        staff = uid in c["staff"]
        if text.startswith("/admin"):
            code = text.split()[-1] if len(text.split()) > 1 else ""
            if code == c["link_code"]:
                with app.lock:
                    c["staff"][uid] = msg.get("from", {}).get("first_name", "")
                    c["link_code"] = f"{random.randint(100000, 999999)}"      # one use
                    app.store.set_setting("telegram", c)
                    app.store.db.commit()
                self.send(token, chat, "تم ربطك بالوكيل الداخلي. اسألني عن المبيعات والمخزون والحجوزات والموقع.\n"
                                       "للتجربة كزبون اكتب /customer وللرجوع /staff")
            else:
                self.send(token, chat, "الرمز غير صحيح.")
            return
        if staff and text in ("/customer", "/staff"):
            self.mode[chat] = text[1:]
            self.send(token, chat, "وضع الزبون: كلمني كأنك زبون." if text == "/customer" else "رجعنا للوكيل الداخلي.")
            return
        if staff and self.mode.get(chat, "staff") == "staff":
            self.call(token, "sendChatAction", {"chat_id": chat, "action": "typing"})
            ans = app.staff.ask(f"tg{uid}", text if not text.startswith("/") else "عطني ملخص اليوم")
            self.send(token, chat, ans)
            return
        # ---- customer: the same sales brain as the website
        if text == "/start":
            text = "السلام عليكم"
        self.call(token, "sendChatAction", {"chat_id": chat, "action": "typing"})
        res = app.agent.chat(f"tg{chat}", text, visitor=f"tg{uid}")
        base = getattr(app, "public_url", "") or ""
        if res.get("text"):
            self.send(token, chat, res["text"].replace("{BASE}", base))
        media = os.path.join(app.store.base_dir, "media", app.store.mode)
        for p in res.get("pieces", [])[:3]:
            cap = f"{p['title']}\nعيار {p['karat']} · {p['weight']} جم\n{p['price']:,} ريال يمني (بسعر اليوم شامل المصنعية)"
            btn = [{"text": "أبغى هذي", "callback_data": f"أبغى {p['code']}"}]
            if base:
                btn.append({"text": "صفحة القطعة", "url": f"{base}/p/{p['code']}"})
            photo = (p.get("photo") or "").split("?")[0].replace("/media/", "")
            fp = os.path.join(media, photo) if photo else ""
            if fp and os.path.isfile(fp):
                self.send_photo(token, chat, fp, cap, btn)
            else:
                self.send(token, chat, cap, btn)
        if res.get("offer"):
            o = res["offer"]
            btn = [{"text": "احجز أو اشترِ من الموقع", "url": f"{base}/p/{o['code']}"}] if base else []
            if o.get("wa"):
                btn.append({"text": "كلّم المبيعات على واتساب", "url": o["wa"].replace("%7BBASE%7D", base).replace("{BASE}", base)})
            self.send(token, chat, f"{o['title']} — {o['price']:,} ريال. اختر الطريقة:", btn or None)
        elif res.get("handoff"):
            self.send(token, chat, "للتواصل مع فريق المبيعات:", [{"text": "واتساب", "url": res["handoff"].replace("%7BBASE%7D", base).replace("{BASE}", base)}])

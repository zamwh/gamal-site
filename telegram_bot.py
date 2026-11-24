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
        self.waiting = {}       # staff chat id -> (piece code, photo role) after pressing a photo button

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

    # ---------- piece photos from the phone: buttons -> send a photo -> saved in its place on the site
    ROLES = (("card", "صورة المخمل"), ("macro", "اللقطة القريبة"), ("orig", "الصورة الأصلية"))

    def _photo_buttons(self, code):
        import core
        with self.app.lock:
            r = core.piece_roles(self.app.store.piece(code))
        return [{"text": ("✓ " if r.get(k) else "+ ") + name, "callback_data": f"ph:{code}:{k}"} for k, name in self.ROLES]

    def piece_alert(self, code):
        """New piece entered in the shop program: ask for its photos."""
        def go():
            try:
                with self.app.lock:
                    c = cfg(self.app.store)
                    p = self.app.store.piece(code)
                token = (c.get("token") or "").strip()
                if not token or not c.get("enabled", True):
                    return
                text = (f"قطعة جديدة {p['code']}\n{p['title'] or p['type']} · {float(p['weight']):.2f} جم\n"
                        "اضغط نوع الصورة وأرسلها، وتنزل في الموقع على طول.")
                for chat in list((c.get("staff") or {}).keys()):
                    self.send(token, chat, text, self._photo_buttons(code))
            except Exception as e:
                print("piece_alert:", e, flush=True)
        threading.Thread(target=go, daemon=True).start()

    def _save_photo(self, token, chat, msg, code, role):
        import core, media
        from web import media_dir
        fid = None
        if msg.get("photo"):
            fid = msg["photo"][-1]["file_id"]
        elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
            fid = msg["document"]["file_id"]
        if not fid:
            return self.send(token, chat, "أرسل صورة.")
        f = self.call(token, "getFile", {"file_id": fid})["result"]
        raw = urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{f['file_path']}", timeout=60).read()
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(raw))
        im.load()
        with self.app.lock:
            s = self.app.store
            logo = getattr(self.app, "base_logo", None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "img", "logo_night.png")
            name = media.save_image(im, media_dir(s), logo, None, role != "card")
            owner = s.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")["id"]
            p = s.set_piece_photos(owner, code, {role: name})
        self.waiting.pop(chat, None)
        names = dict(self.ROLES)
        miss = [names[k] for k, v in core.piece_roles(p).items() if not v]
        self.send(token, chat, f"تم حفظ {names[role]} للقطعة {code} ونزلت في الموقع."
                  + (f"\nباقي: {'، '.join(miss)}" if miss else "\nصور القطعة كاملة."), self._photo_buttons(code) if miss else None)

    def _pending_list(self, token, chat):
        import ops
        with self.app.lock:
            rows = ops.missing_photos(self.app.store, 10)
        if not rows:
            return self.send(token, chat, "كل القطع صورها كاملة.")
        for r in rows:
            self.send(token, chat, f"{r['code']} · {r['title']} · {r['weight']:.2f} جم", self._photo_buttons(r["code"]))

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
        app = self.app
        with app.lock:
            c = cfg(app.store)
        staff = uid in c["staff"]
        # piece photos: a button press, then the photo (or a photo captioned "D000123 مخمل")
        if staff and text.startswith("ph:"):
            _, code, role = (text.split(":") + ["", ""])[:3]
            if role in dict(self.ROLES):
                self.waiting[chat] = (code, role)
                return self.send(token, chat, f"أرسل الحين {dict(self.ROLES)[role]} للقطعة {code}.")
        if staff and (msg.get("photo") or msg.get("document")):
            cap = (msg.get("caption") or "").strip()
            target = self.waiting.get(chat)
            if cap:
                import re as _re
                m = _re.search(r"([A-Za-z]{1,3}\d{3,8})", cap)
                role = "card" if any(w in cap for w in ("مخمل", "عرض")) else "macro" if any(w in cap for w in ("ماكرو", "قريب")) \
                    else "orig" if any(w in cap for w in ("اصل", "أصل", "حقيق")) else (target[1] if target else "card")
                if m:
                    target = (m.group(1).upper(), role)
            if not target:
                return self.send(token, chat, "اضغط أول على نوع الصورة تحت القطعة، أو اكتب مع الصورة رقم القطعة ونوعها مثل: D000123 مخمل")
            try:
                with app.lock:
                    app.store.piece(target[0])
            except Exception:
                return self.send(token, chat, f"ما لقيت قطعة برقم {target[0]}.")
            return self._save_photo(token, chat, msg, target[0], target[1])
        if not chat or not text:
            return
        if staff and text in ("/photos", "/صور"):
            return self._pending_list(token, chat)
        if text.startswith("/admin"):
            code = text.split()[-1] if len(text.split()) > 1 else ""
            if code == c["link_code"]:
                with app.lock:
                    c["staff"][uid] = msg.get("from", {}).get("first_name", "")
                    c["link_code"] = f"{random.randint(100000, 999999)}"      # one use
                    app.store.set_setting("telegram", c)
                    app.store.db.commit()
                self.send(token, chat, "تم ربطك. يوصلك هنا كل بيع وكل حجز وتنبيهات الشراء، وكل قطعة جديدة تطلب صورها.\n"
                                       "اسألني عن المبيعات والمخزون والحجوزات.\n"
                                       "/photos القطع اللي ناقصها صور\n/customer تجربة كزبون، /staff للرجوع")
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

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
        self._ch_last = 0       # last channel check

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

    def upload(self, token, method, fields, files):
        """multipart call with photo files: files = {field name: path}. Returns Telegram's answer; raises on refusal."""
        bnd = uuid.uuid4().hex
        body = b""
        for k, v in fields.items():
            body += f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        for k, path in files.items():
            with open(path, "rb") as f:
                data = f.read()
            body += (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{os.path.basename(path)}\"\r\n"
                     f"Content-Type: {mimetypes.guess_type(path)[0] or 'image/jpeg'}\r\n\r\n").encode() + data + b"\r\n"
        body += f"--{bnd}--\r\n".encode()
        req = urllib.request.Request(API.format(token, method), body, {"Content-Type": f"multipart/form-data; boundary={bnd}"})
        return json.loads(urllib.request.urlopen(req, timeout=90).read())

    def send_photo(self, token, chat, path, caption, buttons=None):
        fields = {"chat_id": str(chat), "caption": caption[:1000]}
        if buttons:
            fields["reply_markup"] = json.dumps({"inline_keyboard": [[b] for b in buttons]}, ensure_ascii=False)
        try:
            self.upload(token, "sendPhoto", fields, {"photo": path})
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
        import tg_channel
        with self.app.lock:
            ch = tg_channel.get(self.app.store)
            to_channel = (not miss and ch.get("id") and ch.get("auto", True) and p["status"] == "available"
                          and p["show_online"] and not tg_channel.posted(self.app.store, code))
        self.send(token, chat, f"تم حفظ {names[role]} للقطعة {code} ونزلت في الموقع."
                  + (f"\nباقي: {'، '.join(miss)}" if miss else "\nصور القطعة كاملة." + (" وبتنزل في قناة المحل خلال دقيقة." if to_channel else "")),
                  self._photo_buttons(code) if miss else None)

    def _pending_list(self, token, chat):
        import ops
        with self.app.lock:
            rows = ops.missing_photos(self.app.store, 10)
        if not rows:
            return self.send(token, chat, "كل القطع صورها كاملة.")
        for r in rows:
            self.send(token, chat, f"{r['code']} · {r['title']} · {r['weight']:.2f} جم", self._photo_buttons(r["code"]))

    # ---------- the shop's channel: new pieces posted by themselves, sold ones marked sold
    def _post_piece(self, token, code):
        import tg_channel
        app = self.app
        with app.lock:
            s = app.store
            ch = tg_channel.get(s)
            p = s.piece(code)
            files, cap = tg_channel.album(s, p, self.username)
        if not ch.get("id"):
            return None
        if not files:                               # photo files missing on disk: skipped after a few tries
            with app.lock:
                tg_channel.failed(app.store, code, "صور القطعة غير موجودة على السيرفر", retry_after=1)
            return None
        try:
            if len(files) == 1:
                r = self.upload(token, "sendPhoto", {"chat_id": ch["id"], "caption": cap, "parse_mode": "HTML"}, {"photo": files[0]})
                mid = r["result"]["message_id"]
            else:
                media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(files))]
                media[0].update(caption=cap, parse_mode="HTML")
                r = self.upload(token, "sendMediaGroup", {"chat_id": ch["id"], "media": json.dumps(media, ensure_ascii=False)},
                                {f"p{i}": f for i, f in enumerate(files)})
                mid = r["result"][0]["message_id"]
        except Exception as e:
            why, wait = str(e), None
            if isinstance(e, urllib.error.HTTPError):
                try:
                    body = json.loads(e.read().decode(errors="ignore") or "{}")
                    why = body.get("description") or why
                    wait = (body.get("parameters") or {}).get("retry_after")
                except Exception:
                    pass
            with app.lock:
                n = tg_channel.failed(app.store, code, why, wait)
                first = n == 1 and ch.get("last_error") != why
            print("channel post:", code, why, flush=True)
            if first and not wait:
                self.notify(f"ما قدرت أنشر القطعة {code} في قناة المحل.\nالسبب من تليجرام: {why}\n"
                            "تأكد إن البوت مشرف في القناة وله صلاحية نشر الرسائل. بحاول مرة ثانية بعد ربع ساعة.")
            return None
        with app.lock:
            tg_channel.record(app.store, code, ch["id"], mid, len(files))
            sold = app.store.piece(code)["status"] == "sold"
        if sold:                                    # sold while it was uploading
            self._mark_sold(token, [code])
        return mid

    def _channel_tick(self, token, force=False):
        import tg_channel
        if not self.username or (not force and time.time() - self._ch_last < tg_channel.EVERY_S):
            return None
        self._ch_last = time.time()
        with self.app.lock:
            p = tg_channel.next_piece(self.app.store)
        return self._post_piece(token, p["code"]) if p else None

    def _mark_sold(self, token, codes):
        import tg_channel
        with self.app.lock:
            s = self.app.store
            rows = tg_channel.unsold_posts(s, codes)
            caps = {r["code"]: tg_channel.caption(s, s.piece(r["code"]), self.username, sold=True) for r in rows}
        for r in rows:
            try:
                self.call(token, "editMessageCaption", {"chat_id": r["chat_id"], "message_id": r["message_id"],
                                                        "caption": caps[r["code"]], "parse_mode": "HTML"})
                ok = True
            except urllib.error.HTTPError as e:
                ok = "not modified" in e.read().decode(errors="ignore")
            except Exception as e:
                print("channel sold:", e, flush=True)
                ok = False
            if ok:
                with self.app.lock:
                    tg_channel.mark_sold(self.app.store, r["code"])

    def channel_sold(self, codes):
        """Called after every sale (store.sold_cb): the piece's post in the channel becomes "تم البيع". Never blocks a sale."""
        def go():
            try:
                with self.app.lock:
                    c = cfg(self.app.store)
                token = (c.get("token") or "").strip()
                if token and c.get("enabled", True):
                    self._mark_sold(token, list(codes or []))
            except Exception as e:
                print("channel_sold:", e, flush=True)
        if codes:
            threading.Thread(target=go, daemon=True).start()

    def _on_member(self, token, m):
        """The bot was added to (or removed from) a channel."""
        import tg_channel
        chat, who = m.get("chat") or {}, str((m.get("from") or {}).get("id", ""))
        new = m.get("new_chat_member") or {}
        if chat.get("type") != "channel":
            return
        st, app = new.get("status"), self.app
        with app.lock:
            c = cfg(app.store)
            cur = tg_channel.get(app.store)
            staff = who in (c.get("staff") or {})
            if st == "administrator" and staff:
                tg_channel.link(app.store, chat, who, new.get("can_post_messages", True))
            elif st == "administrator":
                tg_channel.set_pending(app.store, chat, who)
            elif cur.get("id") == chat.get("id"):
                tg_channel.unlink(app.store)
        if st == "administrator" and staff:
            return self._linked_msg(token, who, chat.get("title") or "", new.get("can_post_messages", True))
        if st == "administrator":
            return self.send(token, who, "وصلني إنك أضفتني للقناة. ربطها يكون من حساب صاحب المحل: "
                                         "أرسل /admin مع الرمز من لوحة الإدارة، وبعدها أرسل /channel")
        if cur.get("id") == chat.get("id"):
            self.notify(f"انفصلت قناة «{cur.get('title', '')}» عن البوت، فوقف النشر فيها.")

    def _linked_msg(self, token, chat, title, can_post=True):
        import tg_channel
        with self.app.lock:
            n = len(tg_channel.seed_candidates(self.app.store))
        text = (f"تم ربط قناة «{title}».\n"
                "أي قطعة جديدة تكتمل صورها تنزل في القناة لحالها، وإذا انباعت يتعدل منشورها إلى «تم البيع».")
        if not can_post:
            text += "\n\nتنبيه: البوت ما عنده صلاحية نشر الرسائل في القناة. فعّلها من إعدادات المشرفين."
        btn = [{"text": f"انشر القطع الموجودة الحين ({n})", "callback_data": "ch:seed"}] if n else None
        self.send(token, chat, text, btn)

    def _channel_cmd(self, token, chat, uid, text):
        import tg_channel
        app = self.app
        with app.lock:
            s = app.store
            pe, cur = tg_channel.pending(s), tg_channel.get(s)
            if text == "ch:seed":
                n = tg_channel.seed(s) if cur.get("id") else 0
                return self.send(token, chat, f"تمام، بتنزل {n} قطعة في القناة، وحدة كل دقيقة." if n else "ما فيه قطع جاهزة للنشر.")
            if text.startswith("ch:auto:") and cur.get("id"):
                tg_channel.set_auto(s, text.endswith(":1"))
                cur = tg_channel.get(s)
                return self.send(token, chat, "النشر التلقائي شغال." if cur.get("auto") else "وقفت النشر التلقائي. تقدر تنشر قطعة بنفسك: /post ورقم القطعة")
            if pe.get("id") and pe.get("id") != cur.get("id"):
                tg_channel.link(s, {"id": pe["id"], "title": pe.get("title"), "username": pe.get("username")}, uid)
                linked = pe.get("title") or ""
            else:
                linked = None
                st = tg_channel.status(s)
        if linked is not None:
            return self._linked_msg(token, chat, linked)
        if not st["linked"]:
            return self.send(token, chat, "قناة المحل مو مربوطة.\n"
                                          "1. سوّ قناة في تليجرام.\n"
                                          f"2. من إعدادات القناة: المشرفين، ثم إضافة مشرف، وابحث عن @{self.username or 'البوت'} واحفظ.\n"
                                          "وترتبط لحالها، ويوصلك تأكيد هنا.")
        btn = [{"text": "وقف النشر التلقائي" if st["auto"] else "شغّل النشر التلقائي", "callback_data": "ch:auto:" + ("0" if st["auto"] else "1")}]
        self.send(token, chat, f"قناة المحل: «{st['title']}»\nنزل فيها {st['posted']} قطعة"
                  + (f"، وباقي {st['queued']} بالدور" if st["queued"] else "") + ".\n"
                  + ("النشر التلقائي شغال." if st["auto"] else "النشر التلقائي موقف.")
                  + (f"\nآخر مشكلة: {st['last_error']}" if st.get("last_error") else "")
                  + "\n/post ورقم القطعة: تنشرها الحين.", btn)

    def _show_piece(self, token, chat, uid, code):
        """A customer tapped a piece's link in the channel: the piece with today's price, and the assistant knows it."""
        app = self.app
        with app.lock:
            try:
                p = app.store.piece(code)
            except Exception:
                p = None
            ok = bool(p) and p["status"] == "available" and bool(p["show_online"])
            pub = app.agent.seed_piece(f"tg{chat}", p["code"]) if ok else None
            br = app.store.one("SELECT name, address FROM branches WHERE id=?", (p["branch_id"],)) if ok else None
        if not ok:
            return self.send(token, chat, ("هذي القطعة انباعت. " if p and p["status"] == "sold" else "هذي القطعة ما عادت معروضة. ")
                             + "قل لي وش تدور عليه وأعرض لك المتوفر.")
        if getattr(app, "analytics", None):
            try:
                app.analytics.log_view(f"telegram-{uid}", p["code"])       # one Telegram account = one person
            except Exception:
                pass
        base = getattr(app, "public_url", "") or ""
        cap = (f"{pub['title']}\nعيار {pub['karat']} · الوزن {float(pub['weight']):.2f} جرام\n"
               + (f"سعرها اليوم {pub['price']:,} ريال يمني شامل المصنعية\n" if pub.get("price") else "")
               + (f"موجودة في {br['name']}" + (f": {br['address']}" if br["address"] else "") + "\n" if br else "")
               + "\nاسألني أي شي عنها، أو قل لي وش تدور عليه.")
        btn = [{"text": "أبغى هذي", "callback_data": f"أبغى {p['code']}"}]
        if base:
            btn.append({"text": "صفحة القطعة", "url": f"{base}/p/{p['code']}"})
        photo = (pub.get("photo") or "").split("?")[0].replace("/media/", "")
        fp = os.path.join(app.store.base_dir, "media", app.store.mode, photo) if photo else ""
        if fp and os.path.isfile(fp):
            self.send_photo(token, chat, fp, cap, btn)
        else:
            self.send(token, chat, cap, btn)

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
                                                    "allowed_updates": ["message", "callback_query", "my_chat_member"]}, timeout=40)
                for u in r.get("result", []):
                    self.offset = u["update_id"] + 1
                    try:
                        self.handle(token, u)
                    except Exception as e:
                        print("telegram handle:", e, flush=True)
                try:
                    self._channel_tick(token)
                except Exception as e:
                    print("channel tick:", e, flush=True)
            except urllib.error.HTTPError as e:
                self.status = f"error {e.code}"
                self.username = ""
                time.sleep(30)
            except Exception as e:
                self.status = "offline"
                time.sleep(10)

    def handle(self, token, u):
        if u.get("my_chat_member"):
            return self._on_member(token, u["my_chat_member"])
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
        if text.lower().startswith("/start p_"):          # a piece's link in the shop's channel
            return self._show_piece(token, chat, uid, text.split("_", 1)[1].strip().upper()[:20])
        if staff and text in ("/photos", "/صور"):
            return self._pending_list(token, chat)
        if staff and (text in ("/channel", "/قناة") or text.startswith("ch:")):
            return self._channel_cmd(token, chat, uid, text)
        if staff and text.startswith("/post"):
            code = (text.split() + [""])[1].strip().upper()
            import tg_channel
            with app.lock:
                ch = tg_channel.get(app.store)
                try:
                    p = app.store.piece(code) if code else None
                except Exception:
                    p = None
                why = ("القناة مو مربوطة، أرسل /channel" if not ch.get("id") else "اكتب رقم القطعة: /post D000123" if not code
                       else f"ما لقيت قطعة برقم {code}." if not p else "القطعة مو معروضة في الموقع أو انباعت." if p["status"] != "available" or not p["show_online"]
                       else "نزلت في القناة قبل." if tg_channel.posted(app.store, code) else "القطعة ما لها صور." if not any(__import__("core").piece_roles(p).values()) else "")
            if why:
                return self.send(token, chat, why)
            return self.send(token, chat, "نزلت في القناة." if self._post_piece(token, code) else "ما قدرت أنشرها الحين، وبحاول مرة ثانية.")
        if text.startswith("/admin"):
            code = text.split()[-1] if len(text.split()) > 1 else ""
            if code == c["link_code"]:
                with app.lock:
                    c["staff"][uid] = msg.get("from", {}).get("first_name", "")
                    c["link_code"] = f"{random.randint(100000, 999999)}"      # one use
                    app.store.set_setting("telegram", c)
                    app.store.db.commit()
                self.send(token, chat, "تم ربطك. يوصلك هنا كل بيع وكل حجز وتنبيهات الشراء، وكل قطعة جديدة تطلب صورها.\n"
                                       "اسألني عن المبيعات والمخزون والحجوزات واهتمام الزبائن بالقطع.\n"
                                       "/photos القطع اللي ناقصها صور\n/channel قناة المحل\n/customer تجربة كزبون، /staff للرجوع")
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

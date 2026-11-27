"""Telegram bot for the shop's staff only: sale/reservation/restock notices, piece photos from the phone, the internal
agent, and the shop's channel. Customers never talk to it: they follow the channel, whose posts lead to the sales team
on WhatsApp and to the website. Anyone else writing to the bot gets a short note pointing there (no AI).
Long-polling with the standard library only. Settings live in the shop database (setting "telegram")."""
import json, mimetypes, os, random, re, secrets, threading, time, urllib.error, urllib.parse, urllib.request, uuid

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
        self._pub = {}          # chat -> last time the "staff only" note went out
        self._admin_fail = {}   # user -> wrong /admin codes in the last hour

    # ---------- telegram calls
    def call(self, token, method, data=None, timeout=35):
        req = urllib.request.Request(API.format(token, method), json.dumps(data or {}).encode(),
                                     {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

    def send(self, token, chat, text, buttons=None, markup=None):
        d = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}
        if buttons:
            d["reply_markup"] = {"inline_keyboard": [[b] for b in buttons]}
        elif markup:
            d["reply_markup"] = markup
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

    def notify_card(self, text, buttons):
        """A short notice with buttons (e.g. a phone call's card: the details only when the owner taps)."""
        def go():
            try:
                with self.app.lock:
                    c = cfg(self.app.store)
                token = (c.get("token") or "").strip()
                if not token or not c.get("enabled", True):
                    return
                for chat in list((c.get("staff") or {}).keys()):
                    if chat not in (c.get("muted") or []):
                        self.send(token, chat, text, buttons)
            except Exception as e:
                print("telegram card:", e, flush=True)
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

    def _pending_list(self, token, chat, kind="none", mid=None):
        """kind "none": pieces with no photo at all; "partial": a photo is in, the velvet/close-up/original missing."""
        import ops, staff_menu
        with self.app.lock:
            rows = ops.missing_photos(self.app.store, 10, kind)
            part = len(ops.missing_photos(self.app.store, 400, "partial")) if kind == "none" else 0
        if kind == "none":
            head = (f"{staff_menu._pcs(len(rows))} بدون أي صورة، تحت كل وحدة أزرار الصور." if rows else "كل القطع لها صور.") \
                + (f"\nوفيه {staff_menu._pcs(part)} ناقصها صورة المخمل أو القريبة: اضغط «ناقصها مخمل أو قريبة»." if part else "")
        else:
            head = f"{staff_menu._pcs(len(rows))} ناقصها صورة، تحت كل وحدة أزرار الصور." if rows else "ما فيه قطع ناقصها صور."
        self._edit(token, chat, mid, head, staff_menu.section_kb("القطع والصور"))
        for r in rows:
            self.send(token, chat, f"{r['code']} · {r['title']} · {r['weight']:.2f} جم", self._photo_buttons(r["code"]))

    def _edit(self, token, chat, mid, text, kb):
        """Rewrite a section's message in place; a new message when there is none to rewrite."""
        if mid:
            try:
                return self.call(token, "editMessageText", {"chat_id": chat, "message_id": mid, "text": text[:4000],
                                                            "reply_markup": kb, "disable_web_page_preview": True})
            except urllib.error.HTTPError as e:
                if "not modified" in e.read().decode(errors="ignore"):
                    return None
            except Exception as e:
                print("edit:", e, flush=True)
        return self.send(token, chat, text, markup=kb)

    def _staff_menu(self, token, chat, uid, text, mid=None):
        """The staff sections (keyboard under the chat) and their options (inside the chat). True when handled."""
        import staff_menu
        app = self.app
        if text.startswith("o:"):
            self._officials(token, chat, uid, text, mid)
            return True
        sec = staff_menu.section_name(text)
        if sec == "قناة المحل":
            self._channel_cmd(token, chat, uid, "/channel")
            return True
        if sec:                                                      # a section button
            with app.lock:
                muted = uid in (cfg(app.store).get("muted") or [])
            self.send(token, chat, staff_menu.INTRO[sec], markup=staff_menu.section_kb(sec, muted if sec == "التنبيهات" else None))
            return True
        if text in ("p:none", "p:part"):
            self._pending_list(token, chat, "none" if text == "p:none" else "partial", mid)
            return True
        if text in ("n:on", "n:off"):
            with app.lock:
                c = cfg(app.store)
                m = [x for x in (c.get("muted") or []) if x != uid] + ([uid] if text == "n:off" else [])
                c["muted"] = m
                app.store.set_setting("telegram", c)
            self._edit(token, chat, mid, "وقفت التنبيهات عندك. تقدر تشغلها من نفس الزر." if text == "n:off" else "رجعت التنبيهات عندك: يوصلك كل بيع وكل حجز.",
                       staff_menu.section_kb("التنبيهات", text == "n:off"))
            return True
        if text in staff_menu.SECTION_OF or text in staff_menu.BUTTONS:
            name = staff_menu.SECTION_OF.get(text)
            try:
                with app.lock:
                    rep = staff_menu.render(app, text)
                    muted = uid in (cfg(app.store).get("muted") or [])
            except Exception as e:
                print("report:", text, e, flush=True)
                rep = "ما قدرت أطلع التقرير الحين."
            if name:
                self._edit(token, chat, mid, rep or "ما فيه بيانات.", staff_menu.section_kb(name, muted if name == "التنبيهات" else None))
            else:
                self.send(token, chat, rep or "ما فيه بيانات.")
            return True
        return False

    # ---------- officials: invite by a one-time link, see who is linked, remove someone
    WELCOME = ("تم ربطك. يوصلك هنا كل بيع وكل حجز وتنبيهات الشراء، وكل قطعة جديدة تطلب صورها.\n"
               "الأقسام في الأزرار تحت، وكل قسم يفتح خياراته هنا. وأي سؤال ثاني اكتبه والوكيل يجاوبك.\n"
               "/customer تجربة المستشار كزبون، /staff للرجوع")

    def _officials(self, token, chat, uid, text, mid=None):
        import staff_menu
        app = self.app
        kb = staff_menu.section_kb("المسؤولين")
        with app.lock:
            c = cfg(app.store)
            staff = dict(c.get("staff") or {})
        if text == "o:add":
            code = secrets.token_hex(6)
            with app.lock:
                c = cfg(app.store)
                inv = {k: v for k, v in (c.get("invites") or {}).items() if time.time() - v.get("ts", 0) < 86400}
                inv[code] = {"by": uid, "ts": time.time()}
                c["invites"] = inv
                app.store.set_setting("telegram", c)
                app.store.db.commit()
            if not self.username:
                return self._edit(token, chat, mid, "البوت للحين ما اتصل، جرّب بعد دقيقة.", kb)
            return self._edit(token, chat, mid, "➕ رابط دعوة لمسؤول جديد:\n"
                              f"https://t.me/{self.username}?start=inv_{code}\n\n"
                              "أرسله للشخص اللي تبغاه. يفتحه ويضغط «ابدأ» وينضاف على طول. "
                              "الرابط يشتغل مرة وحدة خلال 24 ساعة.", kb)
        if text == "o:list":
            lines = [f"• {name or 'بدون اسم'}" + (" (أنت)" if sid == uid else "") for sid, name in staff.items()]
            rows = [[{"text": f"❌ إزالة {name or sid}", "callback_data": f"o:rm:{sid}"}] for sid, name in staff.items() if sid != uid]
            return self._edit(token, chat, mid, f"📋 المسؤولين الحاليين ({len(staff)}):\n" + "\n".join(lines),
                              {"inline_keyboard": rows + kb["inline_keyboard"]})
        if text.startswith("o:rm:"):
            sid = text.split(":", 2)[2]
            if sid not in staff or sid == uid:
                return self._officials(token, chat, uid, "o:list", mid)
            return self._edit(token, chat, mid, f"أزيل {staff[sid] or sid} من المسؤولين؟ ما عاد يوصله شي من البوت.",
                              {"inline_keyboard": [[{"text": "نعم، أزله", "callback_data": f"o:rmy:{sid}"},
                                                    {"text": "لا", "callback_data": "o:list"}]]})
        if text.startswith("o:rmy:"):
            sid = text.split(":", 2)[2]
            if sid == uid or sid not in staff:
                return self._officials(token, chat, uid, "o:list", mid)
            with app.lock:
                c = cfg(app.store)
                name = c["staff"].pop(sid, "")
                c["muted"] = [x for x in (c.get("muted") or []) if x != sid]
                app.store.set_setting("telegram", c)
                app.store.db.commit()
            return self._edit(token, chat, mid, f"تمت إزالة {name or sid}.", kb)
        return None

    def _join(self, token, chat, uid, msg, code):
        """Someone opened an official's invite link."""
        import staff_menu
        app = self.app
        name = (msg.get("from") or {}).get("first_name", "")
        with app.lock:
            c = cfg(app.store)
            if uid in c["staff"]:
                inviter = None
                ok = "already"
            else:
                inv = c.get("invites") or {}
                v = inv.get(code)
                if not v or time.time() - v.get("ts", 0) > 86400:
                    ok, inviter = "expired", None
                else:
                    c["staff"][uid] = name
                    inv.pop(code, None)
                    c["invites"] = inv
                    app.store.set_setting("telegram", c)
                    app.store.db.commit()
                    ok, inviter = "joined", v.get("by")
        if ok == "expired":
            return self.send(token, chat, "الرابط انتهى أو انستخدم. اطلب رابط جديد من أحد المسؤولين.")
        self.send(token, chat, self.WELCOME if ok == "joined" else "أنت مضاف من قبل.", markup=staff_menu.keyboard())
        if inviter and inviter != uid:
            self.send(token, inviter, f"✅ {name or 'مسؤول جديد'} انضاف للمسؤولين.")

    # ---------- the shop's channel: new pieces posted by themselves, sold ones marked sold
    @staticmethod
    def _site(app):
        """The website address for the channel's buttons: the last real one the site was opened on."""
        return (app.store.setting("public_url", "") or "").rstrip("/")

    def _post_piece(self, token, code):
        import tg_channel
        app = self.app
        with app.lock:
            s = app.store
            ch = tg_channel.get(s)
            p = s.piece(code)
            photo = tg_channel.main_photo(s, p)
            cap = tg_channel.caption(s, p)
            kb = tg_channel.buttons(s, p, self._site(app))
        if not ch.get("id"):
            return None
        if not photo:                               # photo file missing on disk: skipped after a few tries
            with app.lock:
                tg_channel.failed(app.store, code, "صور القطعة غير موجودة على السيرفر", retry_after=1)
            return None
        try:
            r = self.upload(token, "sendPhoto", {"chat_id": ch["id"], "caption": cap, "parse_mode": "HTML",
                                                 "reply_markup": json.dumps(kb, ensure_ascii=False)}, {"photo": photo})
            mid = r["result"]["message_id"]
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
            tg_channel.record(app.store, code, ch["id"], mid, kb)
            sold = app.store.piece(code)["status"] == "sold"
        if sold:                                    # sold while it was uploading
            self._mark_sold(token, [code])
        return mid

    def _fix_buttons(self, token, limit=3):
        """The website address or the WhatsApp number changed: old posts get the new buttons, a few a minute."""
        import tg_channel
        with self.app.lock:
            items = tg_channel.stale_buttons(self.app.store, self._site(self.app), limit)
        for r, kb in items:
            try:
                self.call(token, "editMessageReplyMarkup", {"chat_id": r["chat_id"], "message_id": r["message_id"], "reply_markup": kb})
            except urllib.error.HTTPError as e:
                print("channel buttons:", r["code"], e.read().decode(errors="ignore")[:160], flush=True)   # post deleted etc.: don't retry
            except Exception as e:
                print("channel buttons:", e, flush=True)
                continue
            with self.app.lock:
                tg_channel.set_markup(self.app.store, r["code"], kb)

    def _verify_posts(self, token, codes=None):
        """Which recorded posts were deleted from the channel by hand. Asks Telegram to set the same buttons again:
        "not modified" means the post is there, "not found" means it's gone. Nothing visible changes."""
        import tg_channel
        with self.app.lock:
            rows = [r for r in tg_channel.live_posts(self.app.store) if codes is None or r["code"] in codes]
        gone = []
        for r in rows:
            try:
                kb = json.loads(r["markup"]) if r.get("markup") else {"inline_keyboard": []}
                self.call(token, "editMessageReplyMarkup", {"chat_id": r["chat_id"], "message_id": r["message_id"], "reply_markup": kb})
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="ignore").lower()
                if "not found" in body or "message_id_invalid" in body or "can't be edited" in body:
                    gone.append(r["code"])
            except Exception as e:
                print("verify post:", e, flush=True)
        return gone

    def _on_like(self, token, q):
        """«أبغى مثلها» pressed under a sold piece in the channel: counted once per person, a short thank-you,
        and the number on the button goes up. Anyone can press it; nothing else opens."""
        import tg_channel
        code = (q.get("data") or "")[3:].strip().upper()[:20]
        app = self.app
        with app.lock:
            known = app.store.one("SELECT code FROM pieces WHERE code=?", (code,))
            new, n = tg_channel.add_like(app.store, code, (q.get("from") or {}).get("id")) if known else (False, 0)
            kb = tg_channel.buttons(app.store, app.store.piece(code), self._site(app), sold=True) if known else None
        try:
            self.call(token, "answerCallbackQuery", {"callback_query_id": q["id"], "text": (
                "وصل طلبك، شكراً لك. رأيك يحدد البضاعة الجاية." if new else "طلبك مسجل من قبل، شكراً لك.")})
        except Exception:
            pass
        m = q.get("message") or {}
        if new and kb and m.get("message_id"):
            try:
                self.call(token, "editMessageReplyMarkup", {"chat_id": m["chat"]["id"], "message_id": m["message_id"], "reply_markup": kb})
                with app.lock:
                    tg_channel.set_markup(app.store, code, kb)
            except Exception as e:
                print("like count:", e, flush=True)

    def _on_reactions(self, r):
        """Telegram's reaction totals on a channel post (anonymous, grouped, a few minutes late)."""
        import tg_channel
        total = sum(int(x.get("total_count") or 0) for x in r.get("reactions") or [])
        with self.app.lock:
            tg_channel.set_reactions(self.app.store, (r.get("chat") or {}).get("id"), r.get("message_id") or 0, total)

    def _channel_tick(self, token, force=False):
        import tg_channel
        with self.app.lock:
            every = 20 if tg_channel.get(self.app.store).get("queue") else tg_channel.EVERY_S
        if not self.username or (not force and time.time() - self._ch_last < every):
            return None
        self._ch_last = time.time()
        with self.app.lock:
            p = tg_channel.next_piece(self.app.store)
        if p:
            return self._post_piece(token, p["code"])
        self._fix_buttons(token)
        return None

    def _mark_sold(self, token, codes):
        import tg_channel
        with self.app.lock:
            s = self.app.store
            rows = tg_channel.unsold_posts(s, codes)
            caps = {r["code"]: tg_channel.caption(s, s.piece(r["code"]), sold=True) for r in rows}
            kbs = {r["code"]: tg_channel.buttons(s, s.piece(r["code"]), self._site(self.app), sold=True) for r in rows}
        for r in rows:
            try:
                self.call(token, "editMessageCaption", {"chat_id": r["chat_id"], "message_id": r["message_id"],
                                                        "caption": caps[r["code"]], "parse_mode": "HTML",
                                                        "reply_markup": kbs[r["code"]]})
                ok = True
            except urllib.error.HTTPError as e:
                ok = "not modified" in e.read().decode(errors="ignore")
            except Exception as e:
                print("channel sold:", e, flush=True)
                ok = False
            if ok:
                with self.app.lock:
                    tg_channel.mark_sold(self.app.store, r["code"], kbs[r["code"]])

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
        btn = [{"text": f"📤 انشر القطع الموجودة الحين ({n})", "callback_data": "ch:seed"}] if n else None
        self.send(token, chat, text, btn)

    def _channel_cmd(self, token, chat, uid, text):
        import tg_channel
        app = self.app
        with app.lock:
            linked_now = bool(tg_channel.get(app.store).get("id"))
        if text.startswith("ch:") and not linked_now:
            return self.send(token, chat, "القناة مو مربوطة، أرسل /channel")
        if text == "ch:seed":
            gone = self._verify_posts(token)
            with app.lock:
                tg_channel.forget(app.store, gone)
                n = tg_channel.seed(app.store)
            return self.send(token, chat, (f"تمام، بتنزل {n} قطعة في القناة، وحدة كل نص دقيقة تقريباً." if n else "كل القطع المعروضة منشورة في القناة.")
                             + (f"\n{len(gone)} منشور انحذف من القناة، فبتنزل قطعته من جديد." if gone else ""))
        with app.lock:
            s = app.store
            pe, cur = tg_channel.pending(s), tg_channel.get(s)
            auto = None
            if text.startswith("ch:auto:"):
                tg_channel.set_auto(s, text.endswith(":1"))
                auto = tg_channel.get(s).get("auto")
        if auto is not None:                          # Telegram is called outside the lock, so the site never waits on it
            return self.send(token, chat, "▶️ النشر التلقائي شغال." if auto else "⏸️ وقفت النشر التلقائي. تقدر تنشر قطعة بنفسك: /post ورقم القطعة")
        with app.lock:
            s = app.store
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
        btn = [{"text": "📤 انشر القطع الموجودة (والمحذوفة من القناة)", "callback_data": "ch:seed"},
               {"text": "⏸️ وقف النشر التلقائي" if st["auto"] else "▶️ شغّل النشر التلقائي", "callback_data": "ch:auto:" + ("0" if st["auto"] else "1")}]
        self.send(token, chat, f"قناة المحل: «{st['title']}»\nنزل فيها {st['posted']} قطعة"
                  + (f"، وباقي {st['queued']} بالدور" if st["queued"] else "") + ".\n"
                  + ("النشر التلقائي شغال." if st["auto"] else "النشر التلقائي موقف.")
                  + (f"\nآخر مشكلة: {st['last_error']}" if st.get("last_error") else "")
                  + "\n/post ورقم القطعة: تنشرها الحين.", btn)

    def _public_reply(self, token, chat):
        """Someone who is not staff wrote to the bot: one short note (no AI), at most every 10 minutes."""
        now = time.time()
        if now - self._pub.get(chat, 0) < 600:
            return
        if len(self._pub) > 5000:
            self._pub.clear()
        self._pub[chat] = now
        import tg_channel
        with self.app.lock:
            ch = tg_channel.get(self.app.store)
            num = re.sub(r"\D", "", (self.app.store.setting("links", {}) or {}).get("whatsapp", "") or "")
            site = self._site(self.app)
        btn = []
        if ch.get("username"):
            btn.append({"text": "قناة جمال المشرقي", "url": f"https://t.me/{ch['username']}"})
        if num:
            btn.append({"text": "تواصل مع فريق المبيعات", "url": f"https://wa.me/{num}"})
        if site:
            btn.append({"text": "الموقع", "url": site})
        self.send(token, chat, "أهلاً بك. هذا الحساب خاص بإدارة محل جمال المشرقي للذهب والمجوهرات.\n"
                               "تابع قطعنا الجديدة في قناتنا، وللاستفسار تواصل مع فريق المبيعات.", btn or None)

    def _menu_once(self, token):
        """New report buttons: every linked staff account gets them once, without having to ask."""
        import staff_menu
        with self.app.lock:
            c = cfg(self.app.store)
            if c.get("menu_v") == staff_menu.VERSION:
                return
            c["menu_v"] = staff_menu.VERSION
            self.app.store.set_setting("telegram", c)
            chats = list((c.get("staff") or {}).keys())
        for chat in chats:
            self.send(token, chat, "✨ رتبت الأزرار تحت: التقارير، التنبيهات، القطع والصور، قناة المحل، واهتمامات العملاء. وكل قسم يفتح خياراته هنا في المحادثة.",
                      markup=staff_menu.keyboard())

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
                    self._menu_once(token)
                self.status = "running"
                r = self.call(token, "getUpdates", {"offset": self.offset, "timeout": 25,
                                                    "allowed_updates": ["message", "callback_query", "my_chat_member",
                                                                        "message_reaction_count"]}, timeout=40)
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
        if u.get("message_reaction_count"):
            return self._on_reactions(u["message_reaction_count"])
        if u.get("callback_query") and (u["callback_query"].get("data") or "").startswith("lk:"):
            return self._on_like(token, u["callback_query"])
        if u.get("callback_query"):
            q = u["callback_query"]
            self.call(token, "answerCallbackQuery", {"callback_query_id": q["id"]})
            msg = {"chat": q["message"]["chat"], "from": q["from"], "text": q.get("data", ""), "_mid": q["message"].get("message_id")}
        else:
            msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat, uid = msg.get("chat", {}).get("id"), str(msg.get("from", {}).get("id", ""))
        app = self.app
        with app.lock:
            c = cfg(app.store)
        staff = uid in c["staff"]
        if staff and text.startswith("pc:"):           # a phone call's card: its details on request
            with app.lock:
                r = app.store.one("SELECT * FROM phone_calls WHERE id=?", (text[3:20],))
            if not r:
                return self.send(token, chat, "ما لقيت المكالمة.")
            return self.send(token, chat, "تفاصيل مكالمة %s (%s):\n\n%s" % (r["name"], r["phone"], r["transcript"] or "ما فيه كلام مسجل."))
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
        if staff and text in ("/photos", "/صور", "قطع بدون صور"):
            return self._pending_list(token, chat)
        if text.startswith("/start inv_"):
            return self._join(token, chat, uid, msg, text.split("inv_", 1)[1].strip())
        if staff and text in ("/start", "/menu", "/القائمة"):
            import staff_menu
            return self.send(token, chat, "الأقسام في الأزرار تحت، وكل قسم يفتح خياراته هنا. وأي سؤال ثاني اكتبه والوكيل يجاوبك.",
                             markup=staff_menu.keyboard())
        if staff and self._staff_menu(token, chat, uid, text, msg.get("_mid")):
            return
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
                       else "القطعة ما لها صور." if not any(__import__("core").piece_roles(p).values()) else "")
                was = bool(tg_channel.posted(app.store, code)) if not why else False
            if was:
                gone = self._verify_posts(token, [code])
                with app.lock:
                    tg_channel.forget(app.store, gone)
                    if tg_channel.posted(app.store, code):
                        why = "منشورها موجود في القناة."
            if why:
                return self.send(token, chat, why)
            return self.send(token, chat, "نزلت في القناة." if self._post_piece(token, code) else "ما قدرت أنشرها الحين، وبحاول مرة ثانية.")
        if text.startswith("/admin"):
            code = text.split()[-1] if len(text.split()) > 1 else ""
            fails = [t for t in self._admin_fail.get(uid, []) if time.time() - t < 3600]
            if len(fails) >= 5:
                return self.send(token, chat, "محاولات كثيرة. جرّب بعد ساعة.")
            if not code:
                return self.send(token, chat, "اكتب /admin ومعه الرمز اللي في لوحة الإدارة (الإعدادات، مربع بوت التليجرام)، مثل: /admin 123456")
            if code == c["link_code"]:
                with app.lock:
                    c["staff"][uid] = msg.get("from", {}).get("first_name", "")
                    c["link_code"] = f"{random.randint(100000, 999999)}"      # one use
                    app.store.set_setting("telegram", c)
                    app.store.db.commit()
                import staff_menu
                self.send(token, chat, self.WELCOME, markup=staff_menu.keyboard())
            else:
                self._admin_fail[uid] = fails + [time.time()]
                self.send(token, chat, "الرمز غير صحيح.")
            return
        if not staff:                                 # the bot is the shop's tool; customers follow the channel
            if (msg.get("chat") or {}).get("type") == "private":
                self._public_reply(token, chat)
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
        # ---- staff testing as a customer (/customer): the same sales brain as the website
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

# -*- coding: utf-8 -*-
"""Entry point: opens the staff program window and starts the local website for QR scans and the assistant."""
import json
import os
import sys
import threading

import core
from agent import SalesAgent, DEFAULT_AI
from analytics import Analytics
import media
from core import GoldError, Store

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MODE_FILE = os.path.join(core.BASE_DIR, "mode.json")


def read_mode():
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            return json.load(f).get("mode", "demo")
    except (OSError, ValueError):
        return "demo"


def write_mode(mode):
    os.makedirs(core.BASE_DIR, exist_ok=True)
    with open(MODE_FILE, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f)


class App:
    def __init__(self):
        self.lock = threading.RLock()
        self.server = None
        self.base_logo = os.path.join(BASE, "site", "img", "logo_night.png")
        self.load(read_mode())

    def load(self, mode):
        with self.lock:
            if getattr(self, "store", None):
                self.store.close()
            self.store = Store(mode)
            try:
                self.analytics = Analytics(os.path.join(self.store.base_dir, f"analytics-{mode}.db"))
            except Exception:
                self.analytics = None       # analytics must never stop sales
            self.agent = SalesAgent(self.store, self.lock, self.analytics)
            if not getattr(self, "_sync", None):      # branch ↔ server, every 30 s in the background
                import sync_client
                self._sync = sync_client.Worker(self)
                self._sync.start()
            try:
                from core import refresh_demo_photos
                refresh_demo_photos(self.store)
            except Exception:
                pass
            try:
                self.store.daily_backup_if_needed()
            except Exception:
                pass


class Api:
    """Methods called from the staff UI. Every call returns {ok, data} or {ok: False, error}."""

    def __init__(self, app):
        self._app = app
        self._uid = None

    def _run(self, fn, *a, **k):
        try:
            with self._app.lock:
                return {"ok": True, "data": fn(*a, **k)}
        except GoldError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": "خطأ غير متوقع: " + str(e)}

    @property
    def _s(self):
        return self._app.store

    def _need_login(self):
        if not self._uid:
            raise GoldError("سجّل الدخول أولاً")
        return self._uid

    # ---- session
    def info(self):
        def f():
            s = self._s
            return {"mode": s.mode, "shop": s.setting("shop"), "prices": s.current_prices(),
                    "needs_setup": not s.q("SELECT id FROM users LIMIT 1"),
                    "site_url": self._app.server.url() if self._app.server else "",
                    "media_base": f"http://127.0.0.1:{self._app.server.port}/media/" if self._app.server else "",
                    "user": s.user(self._uid) if self._uid else None}
        return self._run(f)

    def login(self, username, password):
        def f():
            u = self._s.login(username, password)
            self._uid = u["id"]
            return u
        return self._run(f)

    def logout(self):
        self._uid = None
        return {"ok": True, "data": None}

    def setup_live(self, owner_name, username, password, branches):
        def f():
            s = self._s
            if s.mode != "live" or s.q("SELECT id FROM users LIMIT 1"):
                raise GoldError("الإعداد الأول متاح مرة واحدة فقط في الوضع الحقيقي")
            names = [b for b in branches if b.get("name", "").strip()]
            if not names:
                raise GoldError("أضف فرعاً واحداً على الأقل")
            for b in names:
                s.db.execute("INSERT INTO branches VALUES (?,?,?,?,?)",
                             (core.new_id(), b["name"].strip(), b.get("address", ""), b.get("phone", ""), ""))
            s.db.commit()
            s.create_user(username, owner_name, "owner", password)
            return True
        return self._run(f)

    def switch_mode(self, mode):
        def f():
            if self._uid:
                self._s.require(self._uid, "owner")
            write_mode(mode)
            self._app.load(mode)
            self._uid = None
            return mode
        try:
            return {"ok": True, "data": f()}
        except GoldError as e:
            return {"ok": False, "error": str(e)}

    def reset_demo(self):
        def f():
            if self._s.mode != "demo":
                raise GoldError("إعادة الضبط متاحة في وضع التجربة فقط")
            self._s.close()
            core.reset_demo()
            self._app.load("demo")
            self._uid = None
            return True
        return self._run(f)

    # ---- prices / branches
    def set_prices(self, p):
        def f():
            r = self._s.set_prices(self._need_login(), **p)
            import sync_client
            sync_client.mark_price_changed(self._s)        # the new price goes to the website and every branch
            return r
        return self._run(f)

    # ---- link to the server (one stock for the three branches and the website)
    def sync_status(self):
        import sync_client
        return self._run(lambda: sync_client.status(self._s))

    def sync_configure(self, d):
        import sync_client
        def f():
            self._s.require(self._need_login(), "owner")
            return sync_client.configure(self._s, d.get("url", ""), d.get("key", ""), d.get("prefix", ""))
        return self._run(f)

    def sync_now(self):
        import sync_client
        return self._run(lambda: sync_client.run_once(self._s))

    def branches(self):
        return self._run(self._s.branches)

    # ---- pieces
    def add_piece(self, p):
        return self._run(lambda: self._s.add_piece(
            self._need_login(), p["type"], p["karat"], p["weight"], p["making_mode"], p["making_value"],
            p["branch_id"], p.get("category", "new"), p.get("cost_per_gram") or None, p.get("notes", ""),
            p.get("show_online", True), p.get("title", ""), p.get("photos") or [], p.get("style", ""),
            p.get("occasion", ""), p.get("description", ""), media=p.get("media") or None))

    def upload_photo(self, data_url, role=None):
        """Staff uploads a photo (from PC or phone): resized, watermarked, stored under media/.
        The styled velvet shot is already finished, so only real photos get the gentle clarity pass."""
        def f():
            self._need_login()
            from web import media_dir
            return media.save_piece_photo(data_url, media_dir(self._s), self._app.base_logo, enhance_it=role != "card")
        return self._run(f)

    def set_piece_photos(self, code, roles):
        return self._run(lambda: self._s.set_piece_photos(self._need_login(), code, roles))

    def piece_photos(self, code):
        def f():
            import core
            p = self._s.piece(code)
            return {"code": p["code"], "title": p["title"] or p["type"], "roles": core.piece_roles(p)}
        return self._run(f)

    def set_piece_media(self, code, d):
        return self._run(lambda: self._s.set_piece_media(self._need_login(), code, d.get("title"), d.get("photos"),
                                                         d.get("style"), d.get("occasion"), d.get("description"),
                                                         d.get("show_online")))

    def list_pieces(self, status=None, branch_id=None, search=""):
        return self._run(lambda: self._s.list_pieces(status or None, branch_id or None, search or ""))

    def piece(self, code):
        def f():
            self._need_login()
            p = self._s.piece(code)
            p["pricing"] = self._s.piece_price(p)
            res = self._s.reservation_for_piece(p["id"])
            p["reservation"] = res
            return p
        return self._run(f)

    def set_piece_status(self, code, status, reason=""):
        return self._run(lambda: self._s.set_piece_status(self._need_login(), code, status, reason))

    def transfer_piece(self, code, to_branch):
        return self._run(lambda: self._s.transfer_piece(self._need_login(), code, to_branch))

    def label(self, code):
        return self._run(lambda: dict(self._s.label(code), url=(self._app.server.url() if self._app.server
                                                                 else "") + "/p/" + code))

    # ---- invoices
    def create_sale(self, d):
        return self._run(lambda: self._s.create_sale(
            self._need_login(), d["items"], d.get("customer_name", ""), d.get("customer_phone", ""),
            d.get("adjust_amount", 0), d.get("adjust_reason", ""), 0, d.get("pay_method")))

    def create_purchase(self, d):
        return self._run(lambda: self._s.create_purchase(
            self._need_login(), d["items"], d.get("customer_name", ""), d.get("customer_phone", ""),
            d.get("customer_id_note", "")))

    def invoice(self, number):
        return self._run(lambda: (self._need_login(), self._s.invoice(number))[1])

    def list_invoices(self, kind=None):
        return self._run(lambda: (self._need_login(), self._s.list_invoices(kind or None))[1])

    def void_invoice(self, number, reason):
        return self._run(lambda: self._s.void_invoice(self._need_login(), number, reason))

    # ---- reservations
    def reservations(self):
        return self._run(lambda: (self._need_login(), self._s.list_reservations())[1])

    def confirm_reservation(self, number):
        return self._run(lambda: self._s.confirm_reservation(self._need_login(), number))

    def close_reservation(self, number, status, note=""):
        return self._run(lambda: self._s.close_reservation(self._need_login(), number, status, note))

    # ---- reports
    def dashboard(self):
        def f():
            self._need_login()
            d = self._s.dashboard()
            d["handoffs"] = self._s.q("SELECT * FROM handoffs WHERE handled=0 ORDER BY id DESC LIMIT 20")
            d["pending_res"] = self._s.one("SELECT COUNT(*) n FROM reservations WHERE status='pending'")["n"]
            return d
        return self._run(f)

    def audit(self):
        return self._run(lambda: (self._s.require(self._need_login(), "owner", "manager"), self._s.audit_log())[1])

    def handoff_done(self, hid):
        return self._run(lambda: (self._need_login(), self._s.db.execute(
            "UPDATE handoffs SET handled=1 WHERE id=?", (hid,)), self._s.db.commit())[0] and True)

    def chat_logs(self):
        return self._run(lambda: (self._s.require(self._need_login(), "owner", "manager"), self._s.q(
            "SELECT session, ts, role, content, skills, cost FROM chat_logs ORDER BY id DESC LIMIT 200"))[1])

    # ---- users / settings
    def users(self):
        return self._run(lambda: (self._s.require(self._need_login(), "owner"), self._s.q(
            "SELECT u.id,u.username,u.name,u.role,u.active,b.name AS branch_name FROM users u "
            "LEFT JOIN branches b ON b.id=u.branch_id ORDER BY u.created_at"))[1])

    def create_user(self, d):
        return self._run(lambda: (self._s.require(self._need_login(), "owner"), self._s.create_user(
            d["username"], d["name"], d["role"], d["password"], d.get("branch_id") or None, by=self._uid))[1])

    def get_settings(self):
        def f():
            self._s.require(self._need_login(), "owner")
            ai = self._app.agent.cfg()
            ai["api_key"] = ("••••" + ai["api_key"][-4:]) if ai.get("api_key") else ""
            return {"shop": self._s.setting("shop"), "reservation": self._s.setting("reservation"),
                    "min_scrap_margin": self._s.setting("min_scrap_margin"),
                    "pound_weight": self._s.setting("pound_weight"), "ai": ai,
                    "links": self._s.setting("links", {}), "payments": self._s.setting("payments", []),
                    "ai_spent": dict(zip(("today", "month"), self._app.agent._spent()))}
        return self._run(f)

    def save_settings(self, d):
        def f():
            uid = self._s.require(self._need_login(), "owner")["id"]
            s = self._s
            if "shop" in d:
                s.set_setting("shop", dict(s.setting("shop"), **d["shop"]))
            if "reservation" in d:
                s.set_setting("reservation", dict(s.setting("reservation"),
                                                  **{k: float(v) for k, v in d["reservation"].items()}))
            for k in ("min_scrap_margin", "pound_weight"):
                if k in d:
                    s.set_setting(k, float(d[k]))
            if "ai" in d:
                ai = dict(s.setting("ai", {}))
                new = d["ai"]
                if new.get("api_key") and not new["api_key"].startswith("••••"):
                    ai["api_key"] = new["api_key"].strip()
                for k in DEFAULT_AI:
                    if k in new and k != "api_key":
                        ai[k] = new[k]
                if ai.get("api_key") and "enabled" not in new:
                    ai["enabled"] = True        # saving a key turns the assistant on
                s.set_setting("ai", ai)
            if "links" in d:
                s.set_setting("links", {k: str(d["links"].get(k, ""))[:200] for k in ("tiktok", "facebook",
                                                                                     "instagram", "whatsapp")})
            if "payments" in d:
                s.set_setting("payments", [{k: str(a.get(k, ""))[:80] for k in ("name", "holder", "account")}
                                           for a in d["payments"]][:8])
            s.log(uid, "settings_change", "settings", None, {k: ("***" if k == "ai" else v) for k, v in d.items()})
            s.db.commit()
            return True
        return self._run(f)

    # ---- website analytics
    def analytics(self, a, b, section="overview"):
        def f():
            self._s.require(self._need_login(), "owner", "manager")
            an = self._app.analytics
            if not an:
                raise GoldError("التحليلات غير متاحة")
            if section == "overview":
                return an.overview(a, b)
            if section == "products":
                rows = an.products(a, b)
                for r in rows:
                    try:
                        p = self._s.piece(r["code"])
                        r.update({"title": p["title"] or p["type"], "status": p["status"],
                                  "photo": __import__("core").card_photo(p)})
                    except GoldError:
                        r.update({"title": r["code"], "status": "?"})
                    r["sold"] = bool(self._s.one(
                        "SELECT 1 FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id JOIN pieces p ON "
                        "p.id=ii.piece_id WHERE p.code=? AND i.kind='sale' AND i.status='ok'", (r["code"],)))
                return rows
            if section == "ai":
                d = an.ai(a, b)
                cfg = self._app.agent.cfg()
                d["projection"] = an.projection(a, b, cfg["price_in"], cfg["price_cached"], cfg["price_out"])
                d["model"] = cfg["model"]
                d["handoffs"] = self._s.one("SELECT COUNT(*) n FROM handoffs WHERE substr(ts,1,10) BETWEEN ? AND ?",
                                            (a, b))["n"]
                # requests (reservation/purchase) that came from sessions that talked to the assistant
                d["requests_from_ai_sessions"] = d.get("requests_after_ai", 0)
                return d
            if section == "funnel":
                return an.funnel(a, b)
            if section == "sessions":
                return an.recent_sessions(a, b)
            raise GoldError("قسم غير معروف")
        return self._run(f)

    def session_path(self, session):
        return self._run(lambda: (self._s.require(self._need_login(), "owner", "manager"),
                                  self._app.analytics.session_path(session))[1])

    def backup_now(self):
        return self._run(lambda: (self._need_login(), self._s.backup())[1])

    def test_chat(self, message, session="staff-test"):
        def f():
            self._need_login()
        r = self._run(f)
        if not r["ok"]:
            return r
        return {"ok": True, "data": self._app.agent.chat(session, message)}


def main():
    import webview
    from web import Server
    app = App()
    try:
        app.server = Server(app, 8080)
        app.server.start()
    except OSError:
        app.server = None
    api = Api(app)
    webview.create_window("جمال المشرقي للذهب والمجوهرات", os.path.join(BASE, "ui", "index.html"),
                          js_api=api, width=1360, height=860, min_size=(1100, 700), background_color="#0b0b0c")
    webview.start(debug=False)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Run the website + assistant + admin on a server (no desktop window).

    python3 server.py --mode demo --port 8095 --data /opt/gamal/data

Open  http://SERVER:PORT/        the website
      http://SERVER:PORT/admin   the owner dashboard (demo login: owner / 123456)
"""
import argparse
import os
import threading
import time

import core
from agent import SalesAgent
from analytics import Analytics
from web import Server


class App:
    def __init__(self, mode, data):
        self.lock = threading.RLock()
        self.store = core.Store(mode, data)
        self.analytics = Analytics(os.path.join(data, f"analytics-{mode}.db"))
        self.agent = SalesAgent(self.store, self.lock, self.analytics)
        from staff_agent import StaffAgent
        self.staff = StaffAgent(self.store, self.lock, self.analytics, self.agent)
        self.public_url = self.store.setting("public_url", "") or ""     # last real address, until the site is opened again
        try:
            n = core.refresh_demo_photos(self.store)
            if n:
                print(f"updated {n} demo photos", flush=True)
        except Exception as e:
            print("photo refresh skipped:", e, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="demo", choices=["demo", "live"])
    ap.add_argument("--port", type=int, default=8095)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--admin-password", default="", help="sets the password of every staff account")
    ap.add_argument("--data", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    a = ap.parse_args()
    os.makedirs(a.data, exist_ok=True)
    app = App(a.mode, a.data)
    if a.admin_password:
        if len(a.admin_password) < 8:
            raise SystemExit("admin password must be at least 8 characters")
        import secrets
        for u in app.store.q("SELECT id FROM users"):
            salt = secrets.token_hex(16)
            app.store.db.execute("UPDATE users SET salt=?, pw_hash=? WHERE id=?",
                                 (salt, core._hash_pw(a.admin_password, salt), u["id"]))
        app.store.db.commit()
    srv = Server(app, a.port, a.host)
    srv.start()
    print(f"site: http://{a.host}:{a.port}/   admin: /admin   mode: {a.mode}", flush=True)

    def tagger():                       # reads the look of new pieces from their photo, a few at a time
        time.sleep(20)
        while True:
            try:
                n = app.agent.tag_traits(6)
                if n:
                    print(f"read the look of {n} pieces", flush=True)
            except Exception as e:
                print("tagger:", e, flush=True)
            time.sleep(600)
    threading.Thread(target=tagger, daemon=True).start()
    import telegram_bot
    app.bot = telegram_bot.Bot(app)
    app.bot.start()
    app.store.notify_cb = app.bot.notify        # every sale, reservation and restock reminder reaches the owner on Telegram
    app.store.piece_cb = app.bot.piece_alert     # a new piece asks for its photos, sent straight from the phone
    app.store.sold_cb = app.bot.channel_sold     # a sold piece's post in the shop's channel becomes "تم البيع"
    app.agent.notify = app.bot.notify            # complaints from customers and the assistant's spending cap reach the owner
    while True:
        time.sleep(3600)
        try:
            with app.lock:
                app.store.daily_backup_if_needed()
        except Exception:
            pass


if __name__ == "__main__":
    main()

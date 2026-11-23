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
    while True:
        time.sleep(3600)
        try:
            with app.lock:
                app.store.daily_backup_if_needed()
        except Exception:
            pass


if __name__ == "__main__":
    main()

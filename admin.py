# -*- coding: utf-8 -*-
"""Web admin (owner/manager/accountant) for the server: analytics, requests review, prices, AI settings, chats.

Auth: username/password from the shop users table -> random session token in an HttpOnly, SameSite=Strict cookie.
"""
import datetime as dt
import json
import os
import re
import secrets
import time

from core import GoldError

SESSIONS = {}          # token -> (user_id, expires)
TTL = 12 * 3600


def _today():
    return dt.date.today()


def login(app, username, password):
    with app.lock:
        u = app.store.login(username, password)
    if u["role"] not in ("owner", "manager", "accountant"):
        raise GoldError("هذا الحساب لا يملك صلاحية لوحة الإدارة")
    tok = secrets.token_urlsafe(32)
    SESSIONS[tok] = (u["id"], time.time() + TTL)
    return tok, u


def user_for(app, cookie_header):
    m = re.search(r"gm_admin=([A-Za-z0-9_-]{20,80})", cookie_header or "")
    if not m:
        return None
    s = SESSIONS.get(m.group(1))
    if not s or s[1] < time.time():
        SESSIONS.pop(m.group(1), None)
        return None
    with app.lock:
        try:
            return app.store.user(s[0])
        except Exception:
            return None


def logout(cookie_header):
    m = re.search(r"gm_admin=([A-Za-z0-9_-]{20,80})", cookie_header or "")
    if m:
        SESSIONS.pop(m.group(1), None)


def _range(q):
    b = q.get("b") or _today().isoformat()
    a = q.get("a") or (_today() - dt.timedelta(days=6)).isoformat()
    for v in (a, b):
        dt.date.fromisoformat(v)
    return a, b


def get(app, u, path, q):
    s, an = app.store, app.analytics
    if path == "/api/admin/me":
        return {"name": u["name"], "role": u["role"], "mode": s.mode}
    if path == "/api/admin/analytics":
        if u["role"] not in ("owner", "manager"):
            raise GoldError("غير مصرح")
        a, b = _range(q)
        sec = q.get("s", "overview")
        if not an:
            raise GoldError("التحليلات غير متاحة")
        if sec == "overview":
            return an.overview(a, b)
        if sec == "funnel":
            return an.funnel(a, b)
        if sec == "products":
            rows = an.products(a, b)
            with app.lock:
                for r in rows:
                    try:
                        p = s.piece(r["code"])
                        ph = json.loads(p["photos"] or "[]")
                        r.update({"title": p["title"] or p["type"], "status": p["status"],
                                  "photo": "/media/" + ph[0] if ph else None})
                    except GoldError:
                        r.update({"title": r["code"], "status": "?"})
            return rows
        if sec == "ai":
            d = an.ai(a, b)
            cfg = app.agent.cfg()
            d["projection"] = an.projection(a, b, cfg["price_in"], cfg["price_cached"], cfg["price_out"])
            d["model"], d["model_strong"] = cfg["model"], cfg.get("model_strong")
            with app.lock:
                d["handoffs"] = s.one("SELECT COUNT(*) n FROM handoffs WHERE substr(ts,1,10) BETWEEN ? AND ?", (a, b))["n"]
            d["spent_today"], d["spent_month"] = app.agent._spent()
            d["caps"] = {"day": cfg["daily_cap_usd"], "month": cfg["monthly_cap_usd"]}
            return d
        if sec == "sessions":
            return an.recent_sessions(a, b, 25)
        raise GoldError("قسم غير معروف")
    if path == "/api/admin/path":
        return app.analytics.session_path(q.get("id", ""))
    if path == "/api/admin/requests":
        with app.lock:
            rows = s.list_reservations()
            return [{k: r[k] for k in ("number", "kind", "status", "customer_name", "customer_phone", "payer_name",
                                       "quoted_price", "amount", "deposit", "created_at", "expires_at", "code", "type",
                                       "weight", "branch_name", "receipt") if k in r.keys()} for r in rows]
    if path == "/api/admin/chats":
        if u["role"] not in ("owner", "manager"):
            raise GoldError("غير مصرح")
        with app.lock:
            return {"chats": s.q("SELECT session, ts, role, content, skills, tokens_in, tokens_out, cost FROM chat_logs "
                                 "ORDER BY id DESC LIMIT 300"),
                    "handoffs": s.q("SELECT * FROM handoffs ORDER BY id DESC LIMIT 50")}
    if path == "/api/admin/settings":
        if u["role"] != "owner":
            raise GoldError("للمالك فقط")
        with app.lock:
            ai = app.agent.cfg()
            ai["api_key"] = ("••••" + ai["api_key"][-4:]) if ai.get("api_key") else ""
            return {"ai": ai, "links": s.setting("links", {}), "payments": s.setting("payments", []),
                    "prices": s.current_prices(), "reservation": s.setting("reservation")}
    raise GoldError("غير موجود")


def post(app, u, path, d):
    s = app.store
    if path == "/api/admin/ai_test":
        s.require(u["id"], "owner")
        return app.agent.test()
    with app.lock:
        if path == "/api/admin/confirm":
            s.confirm_reservation(u["id"], str(d.get("number", "")))
            return {"ok": True}
        if path == "/api/admin/close":
            s.close_reservation(u["id"], str(d.get("number", "")), str(d.get("status", "")), str(d.get("note", ""))[:200])
            return {"ok": True}
        if path == "/api/admin/prices":
            s.set_prices(u["id"], d.get("k21_sell"), d.get("k21_buy"), pound_sell=d.get("pound_sell") or None,
                         pound_buy=d.get("pound_buy") or None, usd_rate=d.get("usd_rate") or None,
                         sar_rate=d.get("sar_rate") or None)
            return {"ok": True}
        if path == "/api/admin/settings":
            s.require(u["id"], "owner")
            if "ai" in d:
                ai = dict(s.setting("ai", {}) or {})
                new = d["ai"]
                key = str(new.get("api_key") or "")
                for k in ("enabled", "model", "model_strong", "daily_cap_usd", "monthly_cap_usd"):
                    if k in new and new[k] not in ("", None):
                        ai[k] = new[k]
                if key and not key.startswith("••••") and key.strip() != ai.get("api_key"):
                    ai["api_key"] = key.strip()
                    ai["enabled"] = True
                s.set_setting("ai", ai)
            if "links" in d:
                s.set_setting("links", {k: str(d["links"].get(k, ""))[:200] for k in
                                        ("tiktok", "facebook", "instagram", "whatsapp")})
            if "payments" in d:
                s.set_setting("payments", [{k: str(a.get(k, ""))[:80] for k in ("name", "holder", "account")}
                                           for a in d["payments"]][:8])
            s.log(u["id"], "settings_change", "settings", None, {"keys": list(d.keys())})
            s.db.commit()
            return {"ok": True}
        if path == "/api/admin/handoff_done":
            s.db.execute("UPDATE handoffs SET handled=1 WHERE id=?", (int(d.get("id", 0)),))
            s.db.commit()
            return {"ok": True}
    raise GoldError("غير موجود")


def receipt_path(app, name):
    if not re.fullmatch(r"[0-9]+_[0-9a-f]+\.(jpg|png)", name or ""):
        return None
    p = os.path.join(app.store.base_dir, "receipts", app.store.mode, name)
    return p if os.path.isfile(p) else None

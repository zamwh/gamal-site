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

import core
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
    if path == "/api/admin/stock":
        if u["role"] not in ("owner", "manager"):
            raise GoldError("غير مصرح")
        try:
            pi = an.piece_interest() if an else {}
        except Exception:
            pi = {}
        with app.lock:
            out = []
            for p in s.list_pieces(search=(q.get("q") or "").strip()):
                if p["status"] == "sold" and not q.get("sold"):
                    continue
                roles = core.piece_roles(p)
                cp = core.card_photo(p)
                out.append({"code": p["code"], "title": (p["title"] if "title" in p.keys() else None) or p["type"],
                            "photos": {k: bool(v) for k, v in roles.items()}, "thumb": "/media/" + cp if cp else None,
                            "type": p["type"], "karat": p["karat"], "weight": p["weight"], "status": p["status"],
                            "branch": p["branch_name"], "online": bool(p["show_online"]),
                            "price": p["price"] if p["status"] != "sold" else None,
                            "views": (pi.get(p["code"]) or [0, 0])[0], "saves": (pi.get(p["code"]) or [0, 0])[1]})
            return out[:300]
    if path == "/api/admin/piece_photos":
        s.require(u["id"], "owner", "manager")
        with app.lock:
            p = s.piece(str(q.get("code", "")))
            roles = core.piece_roles(p)
            return {"code": p["code"], "title": p["title"] or p["type"],
                    "roles": {k: ("/media/" + v if v else None) for k, v in roles.items()}}
    if path == "/api/admin/branches":
        with app.lock:
            return [{"id": b["id"], "name": b["name"]} for b in s.branches()]
    if path == "/api/admin/pos_keys":
        s.require(u["id"], "owner")
        import pos_sync
        with app.lock:
            bid = core.online_branch(s)          # the shop on show: its program is the one to link
            return [dict(k, letter=chr(65 + i), shown=(k["branch_id"] == bid) if bid else True)
                    for i, k in enumerate(pos_sync.keys(s, u["id"]))]
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
                        cp = core.card_photo(p)
                        r.update({"title": p["title"] or p["type"], "status": p["status"],
                                  "photo": "/media/" + cp if cp else None})
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
            v = getattr(app, "voice", None)
            d["voice"] = v.report(a, b) if v else None      # every voice call, by the second, beside the text assistant
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
                                       "weight", "branch_name", "receipt", "pickup") if k in r.keys()} for r in rows]
    if path == "/api/admin/chats":
        if u["role"] not in ("owner", "manager"):
            raise GoldError("غير مصرح")
        with app.lock:
            return {"chats": s.q("SELECT session, ts, role, content, skills, tokens_in, tokens_out, cost FROM chat_logs "
                                 "ORDER BY id DESC LIMIT 300"),
                    "handoffs": s.q("SELECT * FROM handoffs ORDER BY id DESC LIMIT 50")}
    if path == "/api/admin/trace":
        if u["role"] not in ("owner", "manager"):
            raise GoldError("غير مصرح")
        sess = q.get("session") or ""
        with app.lock:
            return {"rows": s.q("SELECT * FROM ai_trace WHERE session=? ORDER BY id", (sess,)) if sess else
                    s.q("SELECT * FROM ai_trace ORDER BY id DESC LIMIT 200")}
    if path == "/api/admin/demand":
        if u["role"] not in ("owner", "manager"):
            raise GoldError("غير مصرح")
        with app.lock:
            rows = s.q("SELECT * FROM demand_requests ORDER BY id DESC LIMIT 300")
            agg = s.q("""SELECT category, COUNT(*) n, ROUND(AVG(NULLIF(budget,0))) avg_budget FROM demand_requests
                         WHERE status='open' GROUP BY category ORDER BY n DESC""")
            return {"rows": rows, "by_category": agg}
    if path == "/api/admin/settings":
        if u["role"] != "owner":
            raise GoldError("للمالك فقط")
        with app.lock:
            ai = app.agent.cfg()
            ai["api_key"] = ("••••" + ai["api_key"][-4:]) if ai.get("api_key") else ""
            return {"ai": ai, "links": s.setting("links", {}), "payments": s.setting("payments", []),
                    "prices": s.current_prices(), "reservation": s.setting("reservation"),
                    "telegram": (lambda c: {"has_token": bool(c.get("token")), "token": ("••••" + c["token"][-4:]) if c.get("token") else "",
                                 "enabled": c.get("enabled", True), "link_code": c.get("link_code"), "staff": len(c.get("staff") or {}),
                                 "status": getattr(getattr(app, "bot", None), "status", "stopped"),
                                 "username": getattr(getattr(app, "bot", None), "username", ""),
                                 "channel": __import__("tg_channel").status(s)})(__import__("telegram_bot").cfg(s)),
                    "policy": dict(__import__("agent").DEFAULT_POLICY, **{k: v for k, v in (s.setting("policy", {}) or {}).items() if (v or "").strip()})}
    raise GoldError("غير موجود")


def post(app, u, path, d):
    s = app.store
    if path == "/api/admin/ai_test":
        s.require(u["id"], "owner")
        return app.agent.test()
    if path == "/api/admin/photo":
        # one photo per request (phones on slow networks): saved, then put in its role
        s.require(u["id"], "owner", "manager")
        role = str(d.get("role", ""))
        if role not in core.PHOTO_ROLES:
            raise GoldError("نوع الصورة غير معروف")
        code = str(d.get("code", "")).strip().upper()
        name = None
        if not d.get("remove"):
            import media
            from web import media_dir
            name = media.save_piece_photo(str(d.get("data", "")), media_dir(s), getattr(app, "base_logo", None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "img", "logo_night.png"), enhance_it=role != "card")
        with app.lock:
            p = s.set_piece_photos(u["id"], code, {role: name})
            return {"ok": True, "roles": {k: ("/media/" + v if v else None) for k, v in core.piece_roles(p).items()}}
    with app.lock:
        if path == "/api/admin/sell":
            # one sale from any branch: recorded in the same sales system the shop uses; the piece turns SOLD at once
            s.require(u["id"], "owner", "manager")
            code = str(d.get("code", "")).strip().upper()
            r = s.create_sale(u["id"], [{"code": code}], str(d.get("name", ""))[:80], str(d.get("phone", ""))[:20])
            return {"ok": True, "invoice": (r.get("number") if isinstance(r, dict) else None)}
        if path == "/api/admin/piece_add":
            s.require(u["id"], "owner", "manager")
            p = s.add_piece(u["id"], str(d.get("type", "")).strip()[:30] or "قطعة", 21, d.get("weight"),
                            "fixed" if d.get("making_mode") == "fixed" else "gram", float(d.get("making_value") or 0),
                            str(d.get("branch_id", "")), "new", None, "", bool(d.get("show_online", True)),
                            str(d.get("title", ""))[:80], [], "", str(d.get("occasion", ""))[:20], str(d.get("description", ""))[:400])
            return {"ok": True, "code": p["code"]}
        if path == "/api/admin/piece_status":
            s.set_piece_status(u["id"], str(d.get("code", "")).upper(), str(d.get("status", "")), str(d.get("reason", ""))[:120])
            return {"ok": True}
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
            if isinstance(d.get("voice"), dict):           # the voice assistant: on/off for the site
                vs = dict(s.setting("voice", {}) or {})
                if "public" in d["voice"]:
                    vs["public"] = bool(d["voice"]["public"])
                s.set_setting("voice", vs)
            if "links" in d:
                s.set_setting("links", {k: str(d["links"].get(k, ""))[:200] for k in
                                        ("tiktok", "facebook", "instagram", "whatsapp")})
            if "payments" in d:
                s.set_setting("payments", [{k: str(a.get(k, ""))[:80] for k in ("name", "holder", "account")}
                                           for a in d["payments"]][:8])
            if "telegram" in d:
                import telegram_bot
                c = telegram_bot.cfg(s)
                tok = str(d["telegram"].get("token") or "").strip()
                if tok and not tok.startswith("••••"):
                    c["token"] = tok
                    if getattr(app, "bot", None):
                        app.bot.username = ""
                if "enabled" in d["telegram"]:
                    c["enabled"] = bool(d["telegram"]["enabled"])
                if d["telegram"].get("unlink_all"):
                    c["staff"] = {}
                if isinstance(c.get("channel"), dict):
                    if "channel_auto" in d["telegram"]:
                        c["channel"]["auto"] = bool(d["telegram"]["channel_auto"])
                    if d["telegram"].get("channel_unlink"):
                        c.pop("channel", None)
                s.set_setting("telegram", c)
            if "policy" in d:
                s.set_setting("policy", {k: str(d["policy"].get(k, ""))[:800] for k in ("returns", "warranty", "branches_near", "hours", "custom_orders", "pounds", "other")})
            s.log(u["id"], "settings_change", "settings", None, {"keys": list(d.keys())})
            s.db.commit()
            return {"ok": True}
        if path == "/api/admin/agent":
            if u["role"] not in ("owner", "manager"):
                raise GoldError("للمالك والمدير")
            return {"text": app.staff.ask(f"web{u['id']}", str(d.get("message", ""))[:1500])}
        if path == "/api/admin/demand_resolve":
            s.db.execute("UPDATE demand_requests SET status='done', resolved_note=? WHERE id=?",
                         (str(d.get("note", ""))[:200], int(d.get("id", 0))))
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

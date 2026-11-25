# -*- coding: utf-8 -*-
"""Website + AI analytics, kept in its own SQLite file (analytics.db) so a failure here never touches sales.

Privacy: anonymous random session/visitor ids from the browser, no names, phones, message text or payment data.
"""
import datetime as dt
import json
import os
import re
import sqlite3
import threading
import time

EVENTS = {
    # site
    "page_view", "piece_view", "search", "filter", "collection_open", "calc_use", "bride_open",
    "shortlist_add", "shortlist_remove", "checkout_start", "terms_accept", "request_submit", "checkout_abandon",
    "whatsapp_click", "social_click", "branch_map",
    # assistant
    "ai_open", "ai_message", "ai_card_shown", "ai_card_click", "ai_detail_open", "ai_suggest_click",
    "ai_set_click", "ai_similar_click", "ai_handoff_click", "ai_add_shortlist", "ai_close",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session TEXT PRIMARY KEY, visitor TEXT, is_new INTEGER, device TEXT, landing TEXT, ref TEXT,
  first_ts TEXT, last_ts TEXT, day TEXT, events INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, eid TEXT UNIQUE, ts TEXT, day TEXT, hour INTEGER, session TEXT,
  type TEXT, page TEXT, code TEXT, value TEXT, via_ai INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_ev_day ON events(day, type);
CREATE INDEX IF NOT EXISTS ix_ev_sess ON events(session);
CREATE INDEX IF NOT EXISTS ix_ev_code ON events(code, type);
CREATE TABLE IF NOT EXISTS ai_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, session TEXT, model TEXT, kind TEXT,
  stage TEXT, skills TEXT, t_in INTEGER, t_cached INTEGER, t_out INTEGER, cost REAL, ms INTEGER, need TEXT);
CREATE INDEX IF NOT EXISTS ix_ai_day ON ai_usage(day);
"""


def _now():
    return dt.datetime.now().replace(microsecond=0)


def _clean(v, n=60):
    v = "" if v is None else str(v)
    return re.sub(r"[\x00-\x1f<>]", "", v)[:n]


class Analytics:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()
        self._rate = {}
        self._pi = (0, {})          # piece interest, cached for a minute

    # ---------- ingest
    def ingest(self, payload):
        """payload: {"s": session, "v": visitor, "n": is_new, "d": device, "r": referrer, "e": [{id,t,p,c,x,a}]}"""
        try:
            sess = _clean(payload.get("s"), 40)
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", sess or ""):
                return 0
            evs = payload.get("e") or []
            if not isinstance(evs, list):
                return 0
            evs = evs[:40]
            now = time.time()
            win = [t for t in self._rate.get(sess, []) if now - t < 60]
            if len(win) > 12:            # max 12 batches/minute per session
                return 0
            self._rate[sess] = win + [now]
            if len(self._rate) > 5000:
                self._rate.clear()
            ts = _now()
            iso, day = ts.isoformat(sep=" "), ts.date().isoformat()
            with self.lock:
                row = self.db.execute("SELECT session FROM sessions WHERE session=?", (sess,)).fetchone()
                if not row:
                    self.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,0)",
                                    (sess, _clean(payload.get("v"), 40), 1 if payload.get("n") else 0,
                                     _clean(payload.get("d"), 10), _clean(payload.get("l"), 80),
                                     _clean(payload.get("r"), 80), iso, iso, day))
                n = 0
                for e in evs:
                    if not isinstance(e, dict) or e.get("t") not in EVENTS:
                        continue
                    cur = self.db.execute(
                        "INSERT OR IGNORE INTO events (eid,ts,day,hour,session,type,page,code,value,via_ai)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (_clean(e.get("id"), 40) or None, iso, day, ts.hour, sess, e["t"], _clean(e.get("p"), 80),
                         _clean(e.get("c"), 20).upper() or None, _clean(e.get("x"), 60) or None,
                         1 if e.get("a") else 0))
                    n += cur.rowcount
                self.db.execute("UPDATE sessions SET last_ts=?, events=events+? WHERE session=?", (iso, n, sess))
                self.db.commit()
            return n
        except Exception:
            return 0      # analytics must never break the site

    def log_ai(self, session, model, kind, stage, skills, t_in, t_cached, t_out, cost, ms, need=""):
        ts = _now()
        try:
            with self.lock:
                self.db.execute("INSERT INTO ai_usage (ts,day,session,model,kind,stage,skills,t_in,t_cached,t_out,"
                                "cost,ms,need) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (ts.isoformat(sep=" "), ts.date().isoformat(), session, model, kind, stage, skills,
                                 t_in, t_cached, t_out, cost, ms, need))
                self.db.commit()
        except Exception:
            pass

    def cost_since(self, day_from):
        r = self.db.execute("SELECT COALESCE(SUM(cost),0) FROM ai_usage WHERE day>=?", (day_from,)).fetchone()
        return float(r[0])

    def piece_interest(self, codes=None):
        """Per piece, since it was listed: how many people opened it (on the site, or from the shop's Telegram channel)
        and how many keep it saved in their list now. A person = one browser or one Telegram account, counted once."""
        if time.time() - self._pi[0] > 60:
            who = "COALESCE(NULLIF(s.visitor,''), e.session)"
            views = self._q(f"""SELECT e.code, COUNT(DISTINCT {who}) n FROM events e LEFT JOIN sessions s ON s.session=e.session
                                WHERE e.type='piece_view' AND e.code IS NOT NULL GROUP BY e.code""")
            saves = self._q(f"""SELECT code, SUM(type='shortlist_add') n FROM (
                                  SELECT e.code, e.type, ROW_NUMBER() OVER (PARTITION BY e.code, {who} ORDER BY e.id DESC) rn
                                  FROM events e LEFT JOIN sessions s ON s.session=e.session
                                  WHERE e.type IN ('shortlist_add','shortlist_remove') AND e.code IS NOT NULL)
                                WHERE rn=1 GROUP BY code""")
            data = {}
            for r in views:
                data.setdefault(r["code"], [0, 0])[0] = r["n"] or 0
            for r in saves:
                if r["n"]:
                    data.setdefault(r["code"], [0, 0])[1] = r["n"]
            self._pi = (time.time(), data)
        data = self._pi[1]
        return dict(data) if codes is None else {c: data[c] for c in codes if c in data}

    # ---------- reports
    def _q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _one(self, sql, args=()):
        r = self._q(sql, args)
        return r[0] if r else {}

    def _prev(self, a, b):
        da, db_ = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        span = (db_ - da).days + 1
        return (da - dt.timedelta(days=span)).isoformat(), (da - dt.timedelta(days=1)).isoformat()

    def _counts(self, a, b):
        s = self._one("""SELECT COUNT(*) sessions, COUNT(DISTINCT visitor) visitors,
                         SUM(is_new) new_visitors FROM sessions WHERE day BETWEEN ? AND ?""", (a, b))
        ev = {r["type"]: r for r in self._q("""SELECT type, COUNT(*) n, COUNT(DISTINCT session) s FROM events
                                               WHERE day BETWEEN ? AND ? GROUP BY type""", (a, b))}
        g = lambda t, k="s": (ev.get(t) or {}).get(k, 0)
        return {
            "visitors": s.get("visitors") or 0, "sessions": s.get("sessions") or 0,
            "new_visitors": s.get("new_visitors") or 0,
            "piece_views": g("piece_view", "n"), "viewers": g("piece_view"),
            "ai_open": g("ai_open"), "ai_chat": g("ai_message"), "ai_card_click": g("ai_card_click"),
            "shortlist": g("shortlist_add"), "checkout": g("checkout_start"), "requests": g("request_submit"),
            "whatsapp": g("whatsapp_click"),
        }

    def overview(self, a, b):
        cur, pa = self._counts(a, b), self._prev(a, b)
        prev = self._counts(*pa)
        dur = self._one("""SELECT AVG((julianday(last_ts)-julianday(first_ts))*86400) d FROM sessions
                           WHERE day BETWEEN ? AND ? AND events>1""", (a, b))
        conv = lambda x, y: round(100.0 * x / y, 1) if y else 0
        cur["avg_duration_s"] = round(dur.get("d") or 0)
        cur["conv_view_to_list"] = conv(cur["shortlist"], cur["viewers"])
        cur["conv_list_to_request"] = conv(cur["requests"], cur["shortlist"])
        cur["conv_visit_to_request"] = conv(cur["requests"], cur["sessions"])
        series = self._q("""SELECT day, COUNT(*) sessions, COUNT(DISTINCT visitor) visitors FROM sessions
                            WHERE day BETWEEN ? AND ? GROUP BY day ORDER BY day""", (a, b))
        evs = {r["day"]: r for r in self._q("""SELECT day, SUM(type='piece_view') views, COUNT(DISTINCT CASE WHEN
                 type='ai_message' THEN session END) ai, SUM(type='request_submit') requests FROM events
                 WHERE day BETWEEN ? AND ? GROUP BY day""", (a, b))}
        for r in series:
            r.update({k: (evs.get(r["day"]) or {}).get(k, 0) or 0 for k in ("views", "ai", "requests")})
        hours = self._q("""SELECT hour, COUNT(DISTINCT session) sessions FROM events WHERE day BETWEEN ? AND ?
                           GROUP BY hour ORDER BY hour""", (a, b))
        exits = self._q("""SELECT e.page, COUNT(*) n FROM events e JOIN (SELECT session, MAX(id) mid FROM events
                           WHERE day BETWEEN ? AND ? GROUP BY session) l ON l.mid=e.id
                           GROUP BY e.page ORDER BY n DESC LIMIT 8""", (a, b))
        searches = self._q("""SELECT value term, COUNT(*) n FROM events WHERE type='search' AND day BETWEEN ? AND ?
                              AND value IS NOT NULL GROUP BY value ORDER BY n DESC LIMIT 10""", (a, b))
        return {"kpi": cur, "prev": prev, "series": series, "hours": hours, "exits": exits, "searches": searches}

    def products(self, a, b):
        rows = self._q("""SELECT code,
              SUM(type='piece_view') views, COUNT(DISTINCT CASE WHEN type='piece_view' THEN session END) viewers,
              SUM(type='ai_card_shown') ai_shown, SUM(type='ai_card_click') ai_clicks,
              SUM(type='shortlist_add') shortlisted, SUM(type='checkout_start') checkouts,
              SUM(type='request_submit') requests
              FROM events WHERE code IS NOT NULL AND day BETWEEN ? AND ? GROUP BY code""", (a, b))
        for r in rows:
            r["interest_no_request"] = (r["views"] or 0) >= 5 and not r["requests"]
            r["view_to_list"] = round(100.0 * (r["shortlisted"] or 0) / r["viewers"], 1) if r["viewers"] else 0
        return rows

    def ai(self, a, b):
        u = self._one("""SELECT COUNT(*) requests, SUM(kind='ai') ai_calls, SUM(kind='canned') canned,
                         COALESCE(SUM(t_in),0) t_in, COALESCE(SUM(t_cached),0) t_cached, COALESCE(SUM(t_out),0) t_out,
                         COALESCE(SUM(cost),0) cost, COUNT(DISTINCT session) sessions, AVG(ms) ms
                         FROM ai_usage WHERE day BETWEEN ? AND ?""", (a, b))
        per_day = self._q("""SELECT day, COALESCE(SUM(cost),0) cost, COUNT(*) msgs, COUNT(DISTINCT session) sessions
                             FROM ai_usage WHERE day BETWEEN ? AND ? GROUP BY day ORDER BY day""", (a, b))
        models = self._q("""SELECT model, COUNT(*) n, COALESCE(SUM(cost),0) cost, COALESCE(SUM(t_in),0) t_in,
                            COALESCE(SUM(t_out),0) t_out FROM ai_usage WHERE day BETWEEN ? AND ? AND kind='ai'
                            GROUP BY model""", (a, b))
        needs = self._q("""SELECT need, COUNT(*) n FROM ai_usage WHERE day BETWEEN ? AND ? AND need<>''
                           GROUP BY need ORDER BY n DESC LIMIT 10""", (a, b))
        stages = self._q("""SELECT stage, COUNT(*) n FROM ai_usage WHERE day BETWEEN ? AND ? GROUP BY stage
                            ORDER BY n DESC""", (a, b))
        msgs_per = self._one("""SELECT AVG(n) m, AVG(d) d FROM (SELECT session, COUNT(*) n,
                               (julianday(MAX(ts))-julianday(MIN(ts)))*86400 d FROM ai_usage
                               WHERE day BETWEEN ? AND ? GROUP BY session)""", (a, b))
        c = self._counts(a, b)
        ev = self._one("""SELECT SUM(type='ai_card_shown') shown, SUM(type='ai_card_click') clicks,
                          SUM(type='ai_detail_open') details, SUM(type='ai_add_shortlist') lists,
                          SUM(type='ai_handoff_click') handoffs FROM events WHERE day BETWEEN ? AND ?""", (a, b))
        after = self._one("""SELECT COUNT(DISTINCT e.session) n FROM events e WHERE e.type='request_submit'
                             AND e.day BETWEEN ? AND ? AND e.session IN (SELECT session FROM events WHERE
                             type='ai_message' AND day BETWEEN ? AND ?)""", (a, b, a, b))
        silent = self._one("""SELECT COUNT(*) n FROM (SELECT session FROM events WHERE day BETWEEN ? AND ?
                              GROUP BY session HAVING SUM(type='ai_message')>0 AND SUM(type IN ('ai_card_click',
                              'ai_detail_open','ai_add_shortlist','ai_handoff_click','request_submit'))=0)""", (a, b))
        top = self._q("""SELECT code, SUM(type='ai_card_shown') shown, SUM(type='ai_card_click') clicks,
                         SUM(type='ai_add_shortlist') lists FROM events WHERE via_ai=1 AND code IS NOT NULL
                         AND day BETWEEN ? AND ? GROUP BY code ORDER BY clicks DESC, shown DESC LIMIT 10""", (a, b))
        sess = u.get("sessions") or 0
        visitors = c["sessions"] or 0
        cost = float(u.get("cost") or 0)
        u.update({
            "cost_per_session": cost / sess if sess else 0,
            "cost_per_message": cost / u["requests"] if u.get("requests") else 0,
            "avg_msgs": round(msgs_per.get("m") or 0, 1), "avg_duration_s": round(msgs_per.get("d") or 0),
            "usage_rate": round(100.0 * (c["ai_chat"] or 0) / visitors, 1) if visitors else 0,
            "cost_per_100_visitors": 100 * cost / visitors if visitors else 0,
            "cost_per_1000_visitors": 1000 * cost / visitors if visitors else 0,
        })
        return {"usage": u, "per_day": per_day, "models": models, "needs": needs, "stages": stages,
                "events": ev, "requests_after_ai": after.get("n") or 0, "silent_sessions": silent.get("n") or 0,
                "top_pieces": top, "opened": c["ai_open"], "chatted": c["ai_chat"]}

    def projection(self, a, b, price_in, price_cached, price_out, daily_visitors=(100, 500, 1000, 3000)):
        """Two clearly separated numbers: MEASURED (from real logs) and SCENARIO (assumptions shown)."""
        ai = self.ai(a, b)["usage"]
        measured = None
        if ai.get("requests"):
            per_msg = float(ai["cost"]) / ai["requests"]
            measured = {"cost_per_message": per_msg, "usage_rate": ai["usage_rate"], "avg_msgs": ai["avg_msgs"],
                        "monthly": [{"visitors": v, "usd": round(v * ai["usage_rate"] / 100 * ai["avg_msgs"] * per_msg * 30, 2)}
                                    for v in daily_visitors]}
        # scenario: 3,500 in (1,500 cached) / 200 out per AI message, 30% answered free (default model only)
        per_ai = ((3500 - 1500) * price_in + 1500 * price_cached + 200 * price_out) / 1e6
        scen = []
        for v in daily_visitors:
            for rate, msgs in ((15, 4), (100, 10)):
                ai_msgs = v * rate / 100 * msgs * 0.7
                scen.append({"visitors": v, "usage_rate": rate, "msgs": msgs,
                             "usd_day": round(ai_msgs * per_ai, 3), "usd_month": round(ai_msgs * per_ai * 30, 2)})
        return {"measured": measured, "scenario": {"per_ai_message": per_ai, "rows": scen,
                "assumptions": "3,500 توكن داخل (1,500 منها مكرر) و200 خارج لكل رسالة، و30% من الأسئلة تُجاب مجاناً"}}

    def funnel(self, a, b):
        steps = [("visit", None), ("piece_view", "piece_view"), ("ai_open", "ai_open"),
                 ("ai_card_shown", "ai_card_shown"), ("ai_card_click", "ai_card_click"),
                 ("shortlist_add", "shortlist_add"), ("checkout_start", "checkout_start"),
                 ("request_submit", "request_submit")]
        total = self._one("SELECT COUNT(*) n FROM sessions WHERE day BETWEEN ? AND ?", (a, b)).get("n") or 0
        out = []
        for key, t in steps:
            n = total if t is None else (self._one("""SELECT COUNT(DISTINCT session) n FROM events WHERE type=?
                                                      AND day BETWEEN ? AND ?""", (t, a, b)).get("n") or 0)
            out.append({"step": key, "sessions": n})
        general = [s for s in out if s["step"] in ("visit", "piece_view", "shortlist_add", "checkout_start",
                                                   "request_submit")]
        ai_path = [s for s in out if s["step"] in ("visit", "ai_open", "ai_card_shown", "ai_card_click",
                                                   "shortlist_add", "request_submit")]
        return {"site": general, "ai": ai_path}

    def session_path(self, session):
        return self._q("SELECT ts, type, page, code, via_ai FROM events WHERE session=? ORDER BY id LIMIT 300",
                       (session,))

    def recent_sessions(self, a, b, limit=40):
        return self._q("""SELECT s.session, s.first_ts, s.last_ts, s.device, s.is_new, s.events,
                          (SELECT COUNT(*) FROM events e WHERE e.session=s.session AND e.type='ai_message') ai_msgs,
                          (SELECT COUNT(*) FROM events e WHERE e.session=s.session AND e.type='request_submit') requests
                          FROM sessions s WHERE s.day BETWEEN ? AND ? ORDER BY s.last_ts DESC LIMIT ?""", (a, b, limit))

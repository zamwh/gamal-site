# -*- coding: utf-8 -*-
"""Shop operations beyond selling: customers, suppliers (accounts and statements), shifts (cash drawer),
stocktake, and owner notifications (every sale, reservations, and "time to restock" by grams sold)."""
import datetime as dt
import json

from core import GoldError, new_id, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT UNIQUE, notes TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT, notes TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supplier_tx (
  id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL, ts TEXT NOT NULL, kind TEXT NOT NULL,
  karat INTEGER, grams REAL NOT NULL DEFAULT 0, amount REAL NOT NULL DEFAULT 0, note TEXT, user_id TEXT);
CREATE TABLE IF NOT EXISTS shifts (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, branch_id TEXT, opened_at TEXT NOT NULL, opening_cash REAL NOT NULL DEFAULT 0,
  closed_at TEXT, counted_cash REAL, expected_cash REAL, note TEXT);
CREATE TABLE IF NOT EXISTS stocktakes (
  id TEXT PRIMARY KEY, branch_id TEXT, user_id TEXT NOT NULL, started_at TEXT NOT NULL, closed_at TEXT,
  status TEXT NOT NULL DEFAULT 'open', scanned TEXT NOT NULL DEFAULT '[]', result TEXT);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT, ref TEXT, seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS channel_posts (
  code TEXT PRIMARY KEY, chat_id TEXT NOT NULL, message_id INTEGER NOT NULL, photos INTEGER NOT NULL DEFAULT 1,
  posted_at TEXT NOT NULL, sold INTEGER NOT NULL DEFAULT 0);
"""


def ensure(s):
    s.db.executescript(SCHEMA)


def _norm_phone(p):
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("967"):
        d = d[3:]
    return d.lstrip("0")[-12:]


# ---------------- notifications
def notify(s, kind, title, body="", ref=None):
    s.db.execute("INSERT INTO notifications (ts,kind,title,body,ref) VALUES (?,?,?,?,?)", (now(), kind, title, body, ref))
    s.db.commit()
    cb = getattr(s, "notify_cb", None)
    if cb:
        try:
            cb(title + ("\n" + body if body else ""))
        except Exception as e:
            print("notify:", e, flush=True)


def notifications(s, limit=60):
    rows = s.q("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))
    unseen = s.one("SELECT COUNT(*) n FROM notifications WHERE seen=0")["n"]
    return {"items": rows, "unseen": unseen}


def mark_seen(s):
    s.db.execute("UPDATE notifications SET seen=1 WHERE seen=0")
    s.db.commit()


def restock_cfg(s):
    c = dict(s.setting("restock", {}) or {})
    c.setdefault("threshold_g", 250)
    c.setdefault("since", None)
    c.setdefault("alerted", 0)
    return c


def grams_since(s, since):
    r = s.one("""SELECT COALESCE(SUM(ii.weight),0) g FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                 WHERE i.kind='sale' AND i.status='ok' AND (? IS NULL OR i.created_at>=?)""", (since, since))
    return round(r["g"], 2)


def restock_state(s):
    c = restock_cfg(s)
    g = grams_since(s, c["since"])
    return {"threshold_g": c["threshold_g"], "since": c["since"], "sold_g": g,
            "due": bool(c["threshold_g"]) and g >= float(c["threshold_g"])}


def restock_done(s, uid, threshold=None):
    s.require(uid, "owner", "manager")
    c = restock_cfg(s)
    c["since"], c["alerted"] = now(), 0
    if threshold is not None:
        c["threshold_g"] = max(0, float(threshold))
    s.set_setting("restock", c)
    s.log(uid, "restock_reset", "settings", None, {"threshold_g": c["threshold_g"]})
    s.db.commit()
    return restock_state(s)


def set_restock_threshold(s, uid, threshold):
    s.require(uid, "owner", "manager")
    c = restock_cfg(s)
    c["threshold_g"] = max(0, float(threshold or 0))
    s.set_setting("restock", c)
    s.db.commit()
    return restock_state(s)


def on_sale(s, inv):
    """Called after every sale: owner notice, customer card, the restock reminder, and "sold" on the shop's channel post."""
    cb = getattr(s, "sold_cb", None)
    if cb:
        try:
            cb([i["code"] for i in inv.get("items", []) if i.get("code")])
        except Exception as e:
            print("sold_cb:", e, flush=True)
    try:
        if inv.get("customer_phone"):
            upsert_customer(s, inv.get("customer_name") or "", inv["customer_phone"])
        grams = sum(float(i["weight"]) for i in inv.get("items", []))
        lines = "\n".join(f"• {i['description']}{' (' + i['code'] + ')' if i.get('code') else ''} — {float(i['weight']):.2f} جم — {i['line_total']:,.0f}"
                          for i in inv.get("items", []))
        notify(s, "sale", f"بيع جديد: {inv['total']:,.0f} ريال — {inv.get('branch_name') or ''}",
               f"فاتورة {inv['number']} · {grams:.2f} جم · البائع {inv.get('user_name') or ''}\n{lines}", inv["number"])
        c = restock_cfg(s)
        g = grams_since(s, c["since"])
        th = float(c["threshold_g"] or 0)
        if th and g >= th and int(g // th) > int(c.get("alerted") or 0):
            c["alerted"] = int(g // th)
            s.set_setting("restock", c)
            notify(s, "restock", f"تنبيه شراء: انباع {g:.0f} جرام من آخر شراء",
                   f"الحد اللي حددته {th:.0f} جرام. لما تشتري، اضغط \"اشتريت\" في التنبيهات عشان يبدأ العد من جديد.")
    except Exception as e:
        print("on_sale:", e, flush=True)


ROLE_AR = {"card": "صورة المخمل", "macro": "اللقطة القريبة", "orig": "الصورة الأصلية"}


def missing_photos(s, limit=30):
    from core import piece_roles
    out = []
    for p in s.q("SELECT * FROM pieces WHERE status IN ('available','reserved') ORDER BY created_at DESC LIMIT 400"):
        r = piece_roles(p)
        miss = [k for k in ("card", "macro", "orig") if not r.get(k)]
        if miss:
            out.append({"code": p["code"], "title": p["title"] or p["type"], "weight": p["weight"], "missing": miss, "roles": r})
        if len(out) >= limit:
            break
    return out


def on_new_piece(s, p):
    try:
        from core import piece_roles
        r = piece_roles(p)
        miss = [ROLE_AR[k] for k in ("card", "macro", "orig") if not r.get(k)]
        title = f"قطعة جديدة {p['code']}: {p['title'] or p['type']} · {float(p['weight']):.2f} جم"
        body = ("ناقصها: " + "، ".join(miss)) if miss else "صورها كاملة"
        s.db.execute("INSERT INTO notifications (ts,kind,title,body,ref) VALUES (?,?,?,?,?)", (now(), "piece", title, body, p["code"]))
        s.db.commit()
        cb = getattr(s, "piece_cb", None)
        if cb and miss:
            cb(p["code"])
    except Exception as e:
        print("on_new_piece:", e, flush=True)


def on_reservation(s, r):
    try:
        notify(s, "reservation", f"طلب {'شراء بتحويل كامل' if r.get('kind') == 'full' else 'حجز بعربون'} جديد — {r['code']}",
               f"رقم الطلب {r['number']} · المبلغ {r['amount']:,.0f} ريال · بانتظار تأكيد وصول التحويل", r["number"])
    except Exception as e:
        print("on_reservation:", e, flush=True)


# ---------------- customers
def upsert_customer(s, name, phone):
    ph = _norm_phone(phone)
    if len(ph) < 7:
        return None
    c = s.one("SELECT * FROM customers WHERE phone=?", (ph,))
    if c:
        if name and not c["name"]:
            s.db.execute("UPDATE customers SET name=? WHERE id=?", (name.strip()[:80], c["id"]))
        return c["id"]
    cid = new_id()
    s.db.execute("INSERT INTO customers (id,name,phone,created_at) VALUES (?,?,?,?)", (cid, (name or "").strip()[:80], ph, now()))
    s.db.commit()
    return cid


def customers(s, search=""):
    rows = s.q("SELECT * FROM customers ORDER BY created_at DESC LIMIT 500")
    inv = s.q("""SELECT customer_phone ph, COUNT(*) n, COALESCE(SUM(total),0) amount, MAX(created_at) last
                 FROM invoices WHERE kind='sale' AND status='ok' AND customer_phone IS NOT NULL AND customer_phone!=''
                 GROUP BY customer_phone""")
    agg = {}
    for r in inv:
        k = _norm_phone(r["ph"])
        a = agg.setdefault(k, {"n": 0, "amount": 0, "last": ""})
        a["n"] += r["n"]
        a["amount"] += r["amount"]
        a["last"] = max(a["last"], r["last"] or "")
    out = []
    q = (search or "").strip()
    for c in rows:
        a = agg.get(c["phone"], {"n": 0, "amount": 0, "last": ""})
        if q and q not in (c["name"] or "") and q not in c["phone"]:
            continue
        out.append(dict(c, invoices=a["n"], amount=a["amount"], last=a["last"]))
    return out


def save_customer(s, uid, d):
    s.require(uid, "owner", "manager", "seller", "accountant")
    ph = _norm_phone(d.get("phone"))
    if len(ph) < 7:
        raise GoldError("رقم الجوال غير صحيح")
    cid = upsert_customer(s, d.get("name") or "", ph)
    s.db.execute("UPDATE customers SET name=?, notes=? WHERE id=?", ((d.get("name") or "").strip()[:80], (d.get("notes") or "")[:300], cid))
    s.db.commit()
    return cid


def customer_invoices(s, phone):
    ph = _norm_phone(phone)
    rows = s.q("SELECT number, total, created_at, customer_phone FROM invoices WHERE kind='sale' AND status='ok' ORDER BY created_at DESC LIMIT 500")
    return [r for r in rows if _norm_phone(r["customer_phone"]) == ph]


# ---------------- suppliers
def suppliers(s):
    rows = s.q("SELECT * FROM suppliers ORDER BY name")
    for r in rows:
        b = supplier_balance(s, r["id"])
        r.update(b)
    return rows


def supplier_balance(s, sid):
    r = s.one("""SELECT COALESCE(SUM(CASE WHEN kind='buy' THEN grams WHEN kind='return' THEN -grams ELSE 0 END),0) g,
                        COALESCE(SUM(CASE WHEN kind IN ('buy') THEN amount WHEN kind IN ('pay','return') THEN -amount ELSE 0 END),0) due
                 FROM supplier_tx WHERE supplier_id=?""", (sid,))
    return {"grams": round(r["g"], 2), "due": round(r["due"], 2)}


def save_supplier(s, uid, d):
    s.require(uid, "owner", "manager", "accountant")
    name = (d.get("name") or "").strip()
    if not name:
        raise GoldError("اكتب اسم المورد")
    if d.get("id"):
        s.db.execute("UPDATE suppliers SET name=?, phone=?, notes=? WHERE id=?", (name[:80], (d.get("phone") or "")[:30], (d.get("notes") or "")[:300], d["id"]))
        sid = d["id"]
    else:
        sid = new_id()
        s.db.execute("INSERT INTO suppliers (id,name,phone,notes,created_at) VALUES (?,?,?,?,?)",
                     (sid, name[:80], (d.get("phone") or "")[:30], (d.get("notes") or "")[:300], now()))
    s.log(uid, "supplier_save", "supplier", sid, {"name": name})
    s.db.commit()
    return sid


def supplier_tx(s, uid, d):
    """kind: buy (gold received: grams + amount owed), pay (money paid to supplier), return (gold sent back)."""
    s.require(uid, "owner", "manager", "accountant")
    kind = d.get("kind")
    if kind not in ("buy", "pay", "return"):
        raise GoldError("نوع الحركة غير معروف")
    if not s.one("SELECT 1 FROM suppliers WHERE id=?", (d.get("supplier_id"),)):
        raise GoldError("المورد غير موجود")
    grams = float(d.get("grams") or 0)
    amount = float(d.get("amount") or 0)
    if kind in ("buy", "return") and grams <= 0:
        raise GoldError("اكتب الوزن بالجرام")
    if kind == "pay" and amount <= 0:
        raise GoldError("اكتب المبلغ المدفوع")
    tid = new_id()
    s.db.execute("INSERT INTO supplier_tx (id,supplier_id,ts,kind,karat,grams,amount,note,user_id) VALUES (?,?,?,?,?,?,?,?,?)",
                 (tid, d["supplier_id"], now(), kind, int(d.get("karat") or 21), grams, amount, (d.get("note") or "")[:200], uid))
    s.log(uid, "supplier_tx", "supplier", d["supplier_id"], {"kind": kind, "grams": grams, "amount": amount})
    s.db.commit()
    if kind == "buy":
        restock_done(s, uid) if s.user(uid)["role"] in ("owner", "manager") else None
    return tid


def supplier_statement(s, sid):
    sup = s.one("SELECT * FROM suppliers WHERE id=?", (sid,))
    if not sup:
        raise GoldError("المورد غير موجود")
    rows = s.q("""SELECT t.*, u.name AS user_name FROM supplier_tx t LEFT JOIN users u ON u.id=t.user_id
                  WHERE supplier_id=? ORDER BY ts""", (sid,))
    g = due = 0.0
    for r in rows:
        if r["kind"] == "buy":
            g += r["grams"]; due += r["amount"]
        elif r["kind"] == "return":
            g -= r["grams"]; due -= r["amount"]
        else:
            due -= r["amount"]
        r["bal_grams"], r["bal_due"] = round(g, 2), round(due, 2)
    return {"supplier": sup, "rows": rows, "balance": supplier_balance(s, sid)}


# ---------------- shifts (cash drawer)
def current_shift(s, uid):
    sh = s.one("SELECT * FROM shifts WHERE user_id=? AND closed_at IS NULL ORDER BY opened_at DESC LIMIT 1", (uid,))
    if sh:
        sh.update(shift_numbers(s, sh))
    return sh


def shift_numbers(s, sh):
    end = sh.get("closed_at") or "9999"
    sales = s.one("""SELECT COUNT(*) n, COALESCE(SUM(total),0) amount,
                            COALESCE(SUM(CASE WHEN pay_method IS NULL OR pay_method='cash' THEN total ELSE 0 END),0) cash
                     FROM invoices WHERE kind='sale' AND status='ok' AND user_id=? AND created_at>=? AND created_at<=?""",
                  (sh["user_id"], sh["opened_at"], end))
    grams = s.one("""SELECT COALESCE(SUM(ii.weight),0) g FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                     WHERE i.kind='sale' AND i.status='ok' AND i.user_id=? AND i.created_at>=? AND i.created_at<=?""",
                  (sh["user_id"], sh["opened_at"], end))
    buys = s.one("""SELECT COUNT(*) n, COALESCE(SUM(total),0) amount FROM invoices
                    WHERE kind='purchase' AND status='ok' AND user_id=? AND created_at>=? AND created_at<=?""",
                 (sh["user_id"], sh["opened_at"], end))
    expected = float(sh["opening_cash"] or 0) + sales["cash"] - buys["amount"]
    return {"sales_n": sales["n"], "sales_amount": sales["amount"], "sales_cash": sales["cash"], "grams": round(grams["g"], 2),
            "buys_n": buys["n"], "buys_amount": buys["amount"], "expected_now": round(expected, 2)}


def open_shift(s, uid, opening_cash=0):
    if current_shift(s, uid):
        raise GoldError("عندك وردية مفتوحة")
    u = s.user(uid)
    sid = new_id()
    s.db.execute("INSERT INTO shifts (id,user_id,branch_id,opened_at,opening_cash) VALUES (?,?,?,?,?)",
                 (sid, uid, u.get("branch_id"), now(), float(opening_cash or 0)))
    s.log(uid, "shift_open", "shift", sid, {"opening_cash": opening_cash})
    s.db.commit()
    return current_shift(s, uid)


def close_shift(s, uid, counted_cash, note=""):
    sh = current_shift(s, uid)
    if not sh:
        raise GoldError("ما فيه وردية مفتوحة")
    s.db.execute("UPDATE shifts SET closed_at=?, counted_cash=?, expected_cash=?, note=? WHERE id=?",
                 (now(), float(counted_cash or 0), sh["expected_now"], (note or "")[:200], sh["id"]))
    s.log(uid, "shift_close", "shift", sh["id"], {"counted": counted_cash, "expected": sh["expected_now"]})
    s.db.commit()
    diff = float(counted_cash or 0) - sh["expected_now"]
    u = s.user(uid)
    notify(s, "shift", f"إغلاق وردية — {u['name']}",
           f"المبيعات {sh['sales_amount']:,.0f} ({sh['sales_n']} فاتورة، {sh['grams']:.2f} جم) · المتوقع في الدرج {sh['expected_now']:,.0f} · "
           f"المعدود {float(counted_cash or 0):,.0f} · {'زيادة' if diff > 0 else 'عجز' if diff < 0 else 'مطابق'} {abs(diff):,.0f}")
    r = s.one("SELECT * FROM shifts WHERE id=?", (sh["id"],))
    r.update(shift_numbers(s, r))
    return r


def shifts(s, limit=60):
    rows = s.q("""SELECT sh.*, u.name AS user_name, b.name AS branch_name FROM shifts sh JOIN users u ON u.id=sh.user_id
                  LEFT JOIN branches b ON b.id=sh.branch_id ORDER BY opened_at DESC LIMIT ?""", (limit,))
    for r in rows:
        r.update(shift_numbers(s, r))
    return rows


# ---------------- stocktake
def stocktake_start(s, uid, branch_id=None):
    s.require(uid, "owner", "manager")
    if s.one("SELECT 1 FROM stocktakes WHERE status='open' AND COALESCE(branch_id,'')=?", (branch_id or "",)):
        raise GoldError("فيه جرد مفتوح لهذا الفرع")
    tid = new_id()
    s.db.execute("INSERT INTO stocktakes (id,branch_id,user_id,started_at) VALUES (?,?,?,?)", (tid, branch_id or None, uid, now()))
    s.log(uid, "stocktake_start", "stocktake", tid, {"branch": branch_id})
    s.db.commit()
    return stocktake_get(s, tid)


def _expected(s, branch_id):
    sql = "SELECT code, type, title, weight, branch_id FROM pieces WHERE status IN ('available','reserved')"
    args = ()
    if branch_id:
        sql += " AND branch_id=?"
        args = (branch_id,)
    return {r["code"]: r for r in s.q(sql, args)}


def stocktake_get(s, tid):
    t = s.one("SELECT st.*, b.name AS branch_name FROM stocktakes st LEFT JOIN branches b ON b.id=st.branch_id WHERE st.id=?", (tid,))
    if not t:
        raise GoldError("الجرد غير موجود")
    scanned = json.loads(t["scanned"] or "[]")
    if t["status"] == "closed" and t["result"]:
        t["result"] = json.loads(t["result"])
        t["scanned"] = scanned
        return t
    exp = _expected(s, t["branch_id"])
    found = [c for c in scanned if c in exp]
    extra = []
    for c in scanned:
        if c not in exp:
            p = s.one("SELECT p.code, p.status, b.name AS branch_name FROM pieces p JOIN branches b ON b.id=p.branch_id WHERE code=?", (c,))
            extra.append({"code": c, "why": ("مسجلة " + {"sold": "مباعة", "inactive": "موقوفة"}.get(p["status"], p["status"]) +
                                             f" — {p['branch_name']}") if p else "غير مسجلة في النظام"})
    missing = [dict(exp[c]) for c in exp if c not in scanned]
    t.update({"scanned": scanned, "expected_n": len(exp), "found_n": len(found),
              "expected_g": round(sum(v["weight"] for v in exp.values()), 2),
              "found_g": round(sum(exp[c]["weight"] for c in found), 2),
              "missing": missing, "extra": extra})
    return t


def stocktake_scan(s, uid, tid, code):
    t = s.one("SELECT * FROM stocktakes WHERE id=?", (tid,))
    if not t or t["status"] != "open":
        raise GoldError("الجرد مغلق")
    code = str(code or "").strip().upper()
    if not code:
        raise GoldError("امسح رقم القطعة")
    sc = json.loads(t["scanned"] or "[]")
    dup = code in sc
    if not dup:
        sc.append(code)
        s.db.execute("UPDATE stocktakes SET scanned=? WHERE id=?", (json.dumps(sc), tid))
        s.db.commit()
    r = stocktake_get(s, tid)
    r["last"] = {"code": code, "dup": dup}
    return r


def stocktake_close(s, uid, tid):
    s.require(uid, "owner", "manager")
    t = stocktake_get(s, tid)
    if t["status"] != "open":
        raise GoldError("الجرد مغلق")
    res = {k: t[k] for k in ("expected_n", "found_n", "expected_g", "found_g", "missing", "extra")}
    s.db.execute("UPDATE stocktakes SET status='closed', closed_at=?, result=? WHERE id=?", (now(), json.dumps(res, ensure_ascii=False), tid))
    s.log(uid, "stocktake_close", "stocktake", tid, {"missing": len(res["missing"]), "extra": len(res["extra"])})
    s.db.commit()
    notify(s, "stocktake", f"انتهى جرد {t.get('branch_name') or 'كل الفروع'}",
           f"المتوقع {res['expected_n']} قطعة ({res['expected_g']} جم) · الموجود {res['found_n']} · ناقص {len(res['missing'])} · زائد {len(res['extra'])}")
    return stocktake_get(s, tid)


def stocktakes(s, limit=30):
    rows = s.q("""SELECT st.id, st.branch_id, st.status, st.started_at, st.closed_at, st.result, b.name AS branch_name, u.name AS user_name
                  FROM stocktakes st LEFT JOIN branches b ON b.id=st.branch_id JOIN users u ON u.id=st.user_id
                  ORDER BY started_at DESC LIMIT ?""", (limit,))
    for r in rows:
        res = json.loads(r.pop("result") or "null")
        r["summary"] = {k: (len(v) if isinstance(v, list) else v) for k, v in (res or {}).items()} if res else None
    return rows

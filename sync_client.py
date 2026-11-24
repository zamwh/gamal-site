"""Branch side of the sync: the shop POS keeps selling with no internet; when the network is there it sends
what happened (new pieces, sales, a new gold price) and takes back the shop-wide stock and price."""
import base64
import io
import json
import os
import threading
import time
import urllib.request

import core


def _cfg(s):
    return dict(s.setting("sync", {}) or {})


def _save(s, c):
    s.set_setting("sync", c)
    s.db.commit()


def configure(s, url, key, prefix):
    c = _cfg(s)
    c.update({"url": url.rstrip("/"), "key": key.strip(), "prefix": prefix.strip().upper()})
    _save(s, c)
    if c["prefix"]:
        s.set_setting("code_prefix", c["prefix"])
        s.db.commit()
    return status(s)


def mark_price_changed(s):
    c = _cfg(s); c["price_pending"] = True; _save(s, c)


def status(s):
    c = _cfg(s)
    return {"linked": bool(c.get("url") and c.get("key")), "url": c.get("url", ""), "prefix": c.get("prefix", ""),
            "last_ok": c.get("last_ok"), "last_error": c.get("last_error"), "queued_sales": len(_pending_sales(s, c)),
            "queued_pieces": len(_pending_pieces(s, c)), "conflicts": c.get("conflicts", [])[-20:]}


def _pending_sales(s, c):
    sent = set(c.get("sent_invoices", []))
    rows = s.q("""SELECT i.number, i.customer_name, i.customer_phone FROM invoices i
                  WHERE i.kind='sale' AND COALESCE(i.status,'')!='void' ORDER BY i.created_at""")
    return [r for r in rows if r["number"] not in sent]


def _pending_pieces(s, c):
    pre = c.get("prefix") or ""
    sent = set(c.get("sent_pieces", []))
    if not pre:
        return []
    return [p for p in s.q("SELECT * FROM pieces WHERE code LIKE ? ORDER BY created_at", (pre + "%",)) if p["code"] not in sent]


def _photo(s, p):
    try:
        ph = json.loads(p.get("photos") or "[]")
        if not ph:
            return None
        from PIL import Image
        im = Image.open(os.path.join(s.base_dir, "media", s.mode, ph[0])); im.thumbnail((1600, 1600))
        b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=86)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


def run_once(s, timeout=25):
    c = _cfg(s)
    if not (c.get("url") and c.get("key")):
        return {"skipped": "not linked"}
    pieces = _pending_pieces(s, c)[:3]                       # photos are heavy: a few per round
    sales = []
    for inv in _pending_sales(s, c)[:50]:
        codes = [r["code"] for r in s.q("""SELECT p.code FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                                            JOIN pieces p ON p.id=ii.piece_id WHERE i.number=?""", (inv["number"],))]
        sales.append({"ref": (c.get("prefix") or "") + "-" + inv["number"], "codes": codes,
                      "customer": inv["customer_name"] or "", "phone": inv["customer_phone"] or "", "_n": inv["number"]})
    body = {"key": c["key"], "sales": [{k: v for k, v in x.items() if k != "_n"} for x in sales],
            "pieces": [{"code": p["code"], "type": p["type"], "karat": p["karat"], "weight": p["weight"],
                        "making_mode": p["making_mode"], "making_value": p["making_value"], "category": p["category"],
                        "show_online": bool(p["show_online"]), "title": p.get("title") or "", "style": p.get("style") or "",
                        "occasion": p.get("occasion") or "", "description": p.get("description") or "", "photo": _photo(s, p)}
                       for p in pieces]}
    pr = s.current_prices()
    if c.get("price_pending") and pr:
        body["price"] = {k: pr.get(k) for k in ("k21_sell", "k21_buy", "pound_sell", "pound_buy")}
    try:
        req = urllib.request.Request(c["url"] + "/api/pos/sync", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read())
    except Exception as e:                                      # offline: keep everything queued, try again later
        c["last_error"] = f"{time.strftime('%H:%M')} — {str(e)[:120]}"; _save(s, c)
        return {"offline": True, "error": str(e)}
    c = _cfg(s)
    done_refs = {a["ref"] for a in res.get("applied", [])} | {x["ref"] for x in res.get("conflicts", [])}
    c["sent_invoices"] = list(set(c.get("sent_invoices", [])) | {x["_n"] for x in sales if x["ref"] in done_refs})[-5000:]
    c["sent_pieces"] = list(set(c.get("sent_pieces", [])) | {x["code"] for x in res.get("pieces", []) if x.get("ok") or x.get("dup")})[-20000:]
    if res.get("conflicts"):
        c["conflicts"] = (c.get("conflicts", []) + res["conflicts"])[-100:]
    if "price" in body:
        c["price_pending"] = False
    # the shop-wide stock: anything this branch still shows as available but the server no longer offers was sold elsewhere
    live = {x["code"] for x in res.get("stock", [])}
    known = set(c["sent_pieces"]) | {x["code"] for x in res.get("stock", [])}
    for p in s.q("SELECT code FROM pieces WHERE status IN ('available','reserved')"):
        if p["code"] in known and p["code"] not in live:
            core.mark_sold_elsewhere(s, p["code"])
    sp = res.get("prices") or {}
    if sp.get("k21_sell") and not c.get("price_pending") and (not pr or pr.get("k21_sell") != sp["k21_sell"] or pr.get("k21_buy") != sp["k21_buy"]):
        owner = s.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")
        if owner:
            s.set_prices(owner["id"], sp["k21_sell"], sp["k21_buy"], pound_sell=sp.get("pound_sell"), pound_buy=sp.get("pound_buy"))
    c["last_ok"] = time.strftime("%Y-%m-%d %H:%M"); c["last_error"] = None
    _save(s, c)
    return {"ok": True, "applied": len(res.get("applied", [])), "conflicts": res.get("conflicts", []), "pieces": res.get("pieces", [])}


class Worker(threading.Thread):
    """Every 30 seconds: send and receive. Never blocks a sale; a failed round simply waits for the next."""
    def __init__(self, app, every=30):
        super().__init__(daemon=True)
        self.app, self.every = app, every

    def run(self):
        while True:
            try:
                with self.app.lock:
                    run_once(self.app.store, timeout=20)
            except Exception:
                pass
            time.sleep(self.every)

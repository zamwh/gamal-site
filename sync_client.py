"""Branch side of the sync: the shop POS keeps selling with no internet; when the network is there it sends
what happened (new pieces, sales, a new gold price) and takes back the shop-wide stock and price."""
import base64
import io
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import core


def _cfg(s):
    return dict(s.setting("sync", {}) or {})


def _save(s, c):
    s.set_setting("sync", c)
    s.db.commit()


def configure(s, url, key, prefix):
    c = _cfg(s)
    if key.strip() and key.strip() != c.get("key"):
        # first link (or a new branch key): sales made before it were trials on this computer; they never reach
        # the website, so a test sale can't sell a real piece. Pieces still go (see _pending_pieces).
        c["sent_invoices"] = list(set(c.get("sent_invoices", [])) |
                                  {r["number"] for r in s.q("SELECT number FROM invoices WHERE kind='sale'")})[-5000:]
        c["server_codes"] = []
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
    """Pieces entered here that the website doesn't have yet: this branch's letter, plus any piece on sale here
    that the server's stock doesn't list (entered before the branch was linked, under another letter)."""
    pre = c.get("prefix") or ""
    sent = set(c.get("sent_pieces", []))
    out = [p for p in s.q("SELECT * FROM pieces WHERE code LIKE ? ORDER BY created_at", (pre + "%",)) if p["code"] not in sent] if pre else []
    known = set(c.get("server_codes") or [])
    if known:                                   # learned on the first round after linking
        have = {p["code"] for p in out}
        out += [p for p in s.q("SELECT * FROM pieces WHERE status IN ('available','reserved') ORDER BY created_at")
                if p["code"] not in known and p["code"] not in sent and p["code"] not in have]
    return out


def _file_url(s, name):
    try:
        from PIL import Image
        im = Image.open(os.path.join(s.base_dir, "media", s.mode, name)); im.thumbnail((1600, 1600))
        b = io.BytesIO(); im.convert("RGB").save(b, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


def _photo(s, p):
    from core import original_photo
    f = original_photo(p)
    return _file_url(s, f) if f else None


def _show(p):
    k = p.keys()
    return {"new_until": p["new_until"] if "new_until" in k else None, "featured": int(p["featured"] or 0) if "featured" in k else 0,
            "featured_until": p["featured_until"] if "featured_until" in k else None}


def _ph_sig(p):
    from core import piece_roles
    return json.dumps(piece_roles(p), sort_keys=True)


def _media_sig(p):
    """photos + showcase (new arrival / featured): a change in either is sent to the server"""
    return {"ph": _ph_sig(p), "sh": json.dumps(_show(p), sort_keys=True)}


def _media(s, p):
    from core import piece_roles
    # only photos set here travel; a photo added on the server (e.g. from the phone) is never erased by a branch
    return {k: _file_url(s, v) for k, v in piece_roles(p).items() if v}


def _pending_media(s, c):
    """Pieces already on the server whose photos changed here (e.g. the velvet shots added later)."""
    pre = c.get("prefix") or ""
    if not pre:
        return []
    sent, sigs = set(c.get("sent_pieces", [])), c.get("sent_media", {})
    return [p for p in s.q("SELECT * FROM pieces WHERE code LIKE ? ORDER BY updated_at DESC", (pre + "%",))
            if p["code"] in sent and sigs.get(p["code"]) != _media_sig(p)]


def _pull_photos(s, c, stock, limit=6):
    from core import piece_roles, PHOTO_ROLES
    folder = os.path.join(s.base_dir, "media", s.mode)
    os.makedirs(folder, exist_ok=True)
    n = 0
    sigs = c.setdefault("sent_media", {})
    for x in stock:
        srv = x.get("media") or {}
        p = s.one("SELECT * FROM pieces WHERE code=?", (x["code"],))
        if not p or not any(srv.values()):
            continue
        loc = piece_roles(p)
        want = {k: srv[k] for k in PHOTO_ROLES if srv.get(k) and not loc.get(k)}
        if not want:
            continue
        got = {}
        for k, name in want.items():
            if n >= limit:
                break
            fp = os.path.join(folder, name)
            if not os.path.exists(fp):
                with urllib.request.urlopen(c["url"] + "/media/" + urllib.parse.quote(name), timeout=30) as r:
                    data = r.read()
                with open(fp, "wb") as f:
                    f.write(data)
                n += 1
            got[k] = name
        if got:
            merged = dict(loc, **got)
            ordered = [merged[k] for k in PHOTO_ROLES if merged.get(k)]
            s.db.execute("UPDATE pieces SET media=?, photos=? WHERE id=?", (json.dumps(merged), json.dumps(ordered), p["id"]))
            s.db.commit()
            if x["code"] in set(c.get("sent_pieces", [])):
                sigs[x["code"]] = _media_sig(s.one("SELECT * FROM pieces WHERE id=?", (p["id"],)))   # came from the server: nothing to send back
    _save(s, c)


def run_once(s, timeout=25):
    c = _cfg(s)
    if not (c.get("url") and c.get("key")):
        return {"skipped": "not linked"}
    pend = _pending_pieces(s, c)
    waiting = {p["code"] for p in pend}
    sales, need = [], []
    for inv in _pending_sales(s, c)[:50]:
        codes = [r["code"] for r in s.q("""SELECT p.code FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                                            JOIN pieces p ON p.id=ii.piece_id WHERE i.number=?""", (inv["number"],))]
        if waiting & set(codes):            # a piece of this sale is not on the server yet: send it first, the sale next round
            need += [x for x in codes if x in waiting]
            continue
        sales.append({"ref": (c.get("prefix") or "") + "-" + inv["number"], "codes": codes,
                      "customer": inv["customer_name"] or "", "phone": inv["customer_phone"] or "", "_n": inv["number"]})
    pieces, nph = [], 0
    for p in sorted(pend, key=lambda p: p["code"] not in need):       # photos are heavy: about four per round
        k = max(1, sum(1 for v in __import__("core").piece_roles(p).values() if v))
        if pieces and nph + k > 4:
            break
        pieces.append(p); nph += k
    body = {"key": c["key"], "sales": [{k: v for k, v in x.items() if k != "_n"} for x in sales],
            "pieces": [{"code": p["code"], "type": p["type"], "karat": p["karat"], "weight": p["weight"],
                        "making_mode": p["making_mode"], "making_value": p["making_value"], "category": p["category"],
                        "show_online": bool(p["show_online"]), "title": p.get("title") or "", "style": p.get("style") or "",
                        "occasion": p.get("occasion") or "", "description": p.get("description") or "", "photo": _photo(s, p),
                        "media": _media(s, p), "showcase": _show(p)}
                       for p in pieces]}
    upd = _pending_media(s, c)[:2] if len(pieces) < 2 else []
    if upd:
        sigs0 = c.get("sent_media", {})
        body["media_updates"] = [dict({"code": p["code"], "showcase": _show(p)},
                                      **({"media": _media(s, p)} if (sigs0.get(p["code"]) if isinstance(sigs0.get(p["code"]), dict) else {}).get("ph") != _ph_sig(p) else {}))
                                 for p in upd]
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
    sigs = c.get("sent_media", {})
    byc = {p["code"]: p for p in pieces + upd}
    for x in res.get("pieces", []) + res.get("media", []):
        if (x.get("ok") or x.get("dup")) and x.get("code") in byc:
            sigs[x["code"]] = _media_sig(byc[x["code"]])
    c["sent_media"] = sigs
    if res.get("conflicts"):
        c["conflicts"] = (c.get("conflicts", []) + res["conflicts"])[-100:]
    if "price" in body:
        c["price_pending"] = False
    # the shop-wide stock: anything this branch still shows as available but the server no longer offers was sold elsewhere
    live = {x["code"] for x in res.get("stock", [])}
    c["server_codes"] = sorted(live)[-20000:]
    known = set(c["sent_pieces"]) | {x["code"] for x in res.get("stock", [])}
    for p in s.q("SELECT code FROM pieces WHERE status IN ('available','reserved')"):
        if p["code"] in known and p["code"] not in live:
            core.mark_sold_elsewhere(s, p["code"])
    # photos added on the server (from the phone or Telegram) come down, so the cashier shows them too
    try:
        _pull_photos(s, c, res.get("stock", []))
    except Exception as e:
        print("photo pull:", e, flush=True)
    sp = res.get("prices") or {}
    if sp.get("k21_sell") and not c.get("price_pending") and (not pr or pr.get("k21_sell") != sp["k21_sell"] or pr.get("k21_buy") != sp["k21_buy"]):
        owner = s.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")
        if owner:
            s.set_prices(owner["id"], sp["k21_sell"], sp["k21_buy"], pound_sell=sp.get("pound_sell"), pound_buy=sp.get("pound_buy"))
    if isinstance(res.get("interest"), dict):            # views / saves per piece from the website, for the pieces screen
        s.set_setting("piece_interest", {"at": time.strftime("%Y-%m-%d %H:%M"),
                                         "by_code": {str(k)[:20]: [int(v[0]), int(v[1])] for k, v in res["interest"].items()
                                                     if isinstance(v, (list, tuple)) and len(v) == 2}})
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

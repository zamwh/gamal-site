"""Branch POS ↔ server sync.

The shop POS (.exe) sells offline in each branch and keeps a queue. When the network is there it calls
POST /api/pos/sync with its branch key. The server — the single source of truth — applies every queued sale
in one place, so a piece can only be sold once across the three branches and the website. It answers with the
current stock and gold price, so every branch and the site see the same thing.

Conflicts (the same piece sold offline in two branches) are never silently dropped: the second sale is returned
as a conflict and logged for the accountant.
"""
import hmac
import secrets

from core import GoldError


def keys(store, owner_id):
    """One key per branch, created on first use; only the owner sees them (admin → settings)."""
    k = dict(store.setting("pos_keys", {}) or {})
    changed = False
    for b in store.branches():
        if str(b["id"]) not in k:
            k[str(b["id"])] = "gm_" + secrets.token_urlsafe(24)
            changed = True
    if changed:
        store.set_setting("pos_keys", k)
        store.log(owner_id, "pos_keys_created", "settings", None, {})
        store.db.commit()
    return [{"branch_id": b["id"], "branch": b["name"], "key": k[str(b["id"])]} for b in store.branches()]


def _branch_for(store, key):
    for bid, k in (store.setting("pos_keys", {}) or {}).items():
        if key and hmac.compare_digest(str(k), str(key)):
            return bid
    raise GoldError("مفتاح الفرع غير صحيح")


def _branch_user(store, branch_id):
    """A dedicated system seller per branch, so every synced sale is traceable to its branch."""
    name = f"pos_branch_{branch_id}"
    u = store.one("SELECT id FROM users WHERE username=?", (name,))
    if u:
        return u["id"]
    owner = store.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")["id"]
    store.create_user(name, f"برنامج المحل — فرع {branch_id}", "seller", secrets.token_urlsafe(18), branch_id, by=owner)
    return store.one("SELECT id FROM users WHERE username=?", (name,))["id"]


def sync(store, data):
    branch_id = _branch_for(store, data.get("key"))
    uid = _branch_user(store, branch_id)
    applied, conflicts, pieces_in = [], [], []
    # new pieces entered at the branch: the server becomes their home, so the website and every branch see them
    import media, os
    for np in (data.get("pieces") or [])[:100]:
        code = str(np.get("code", "")).strip().upper()
        if not code or store.one("SELECT 1 FROM pieces WHERE code=?", (code,)):
            pieces_in.append({"code": code, "dup": True})
            continue
        photos = []
        if np.get("photo"):
            try:
                folder = os.path.join(store.base_dir, "media", store.mode); os.makedirs(folder, exist_ok=True)
                photos = [media.save_piece_photo(np["photo"], folder)]
            except Exception:
                photos = []
        try:
            store.add_piece(uid, np["type"], np["karat"], np["weight"], np.get("making_mode", "gram"), np.get("making_value", 0),
                            branch_id, np.get("category", "new"), None, str(np.get("notes", ""))[:200], bool(np.get("show_online", True)),
                            str(np.get("title", ""))[:80], photos, str(np.get("style", ""))[:20], str(np.get("occasion", ""))[:20],
                            str(np.get("description", ""))[:400], code=code)
            pieces_in.append({"code": code, "ok": True})
        except Exception as e:
            pieces_in.append({"code": code, "error": str(e)[:120]})
    for s in (data.get("sales") or [])[:200]:
        ref = str(s.get("ref", ""))[:40]
        codes = [str(c).strip().upper() for c in (s.get("codes") or [])][:30]
        if not codes:
            continue
        # idempotent: a retried sync must not sell twice
        if ref and store.one("SELECT 1 FROM audit WHERE action='pos_sale' AND details LIKE ?", (f'%"ref": "{ref}"%',)):
            applied.append({"ref": ref, "dup": True})
            continue
        try:
            inv = store.create_sale(uid, [{"code": c} for c in codes], str(s.get("customer", ""))[:80],
                                    str(s.get("phone", ""))[:20])
            store.log(uid, "pos_sale", "invoice", None, {"ref": ref, "invoice": inv["number"], "codes": codes})
            store.db.commit()
            applied.append({"ref": ref, "invoice": inv["number"]})
        except GoldError as e:
            store.log(uid, "pos_conflict", "piece", None, {"ref": ref, "codes": codes, "error": str(e)})
            store.db.commit()
            conflicts.append({"ref": ref, "codes": codes, "error": str(e)})
    pr = data.get("price")
    if pr and pr.get("k21_sell") and pr.get("k21_buy"):
        owner = store.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")["id"]
        store.set_prices(owner, pr["k21_sell"], pr["k21_buy"], pound_sell=pr.get("pound_sell") or None,
                         pound_buy=pr.get("pound_buy") or None)
    stock = [{"code": p["code"], "status": p["status"], "type": p["type"], "weight": p["weight"], "karat": p["karat"],
              "branch_id": p["branch_id"], "title": (p["title"] if "title" in p.keys() else None) or p["type"]}
             for p in store.list_pieces() if p["status"] in ("available", "reserved")]
    cur = store.current_prices() or {}
    return {"ok": True, "branch_id": branch_id, "applied": applied, "conflicts": conflicts, "pieces": pieces_in, "stock": stock,
            "prices": {k: cur.get(k) for k in ("k21_sell", "k21_buy", "pound_sell", "pound_buy", "created_at")}}

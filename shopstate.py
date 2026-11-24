"""Structured shopping-session state, kept by the backend (never by the model's memory).

state = {
  "request": {category, occasion, budget, currency, weight_max, required[], excluded[], branch, pay_method, intent},
  "shown":   [{code, title, kind, price, weight, karat, photo, reason, turn, batch, clicked, liked, rejected,
               reject_reason, selected}],
  "turn": n, "batch": n, "selected": code | None
}
Everything here is plain Python and is tested without any AI (tests/eval_backend.py).
"""
import json, re, time

AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
BACK = ["اللي عرضته قبل", "السابق", "اللي قبل", "ارجع", "نفس القطعه", "نفسه", "الطقم الاول", "اللي قبله"]
LAST = ["الاخير", "اللي بعده", "هذا", "هذي", "ذا", "اياه"]


def norm(t):
    return re.sub(r"[ًٌٍَُِّْـ]", "", (t or "").translate(AR)).lower()


def new_state():
    return {"request": {"excluded": [], "required": []}, "shown": [], "turn": 0, "batch": 0, "selected": None}


def load(raw):
    try:
        s = json.loads(raw) if raw else None
    except Exception:
        s = None
    if not isinstance(s, dict):
        s = new_state()
    base = new_state()
    for k, v in base.items():
        s.setdefault(k, v)
    s["request"].setdefault("excluded", [])
    s["request"].setdefault("required", [])
    return s


def update_request(state, **kw):
    r = state["request"]
    for k, v in kw.items():
        if v in (None, "", []):
            continue
        if k in ("excluded", "required"):
            r[k] = list(dict.fromkeys(list(r.get(k) or []) + list(v)))
        else:
            r[k] = v
    # a feature the customer now asks for is no longer excluded (they changed their mind)
    if r.get("required"):
        r["excluded"] = [x for x in r["excluded"] if x not in r["required"]]
    return r


def drop_exclusion(state, feature):
    state["request"]["excluded"] = [x for x in state["request"]["excluded"] if x != feature]


def register_shown(state, pieces, reasons=None):
    """pieces: public dicts {code,title,kind,price,weight,karat,photo}. One call = one batch shown in one reply."""
    if not pieces:
        return
    state["batch"] += 1
    reasons = reasons or {}
    for p in pieces:
        e = find(state, p["code"])
        if e:                                    # shown again: refresh price/turn, keep its history
            e.update(price=p["price"], turn=state["turn"], batch=state["batch"])
            continue
        state["shown"].append({"code": p["code"], "title": p.get("title"), "kind": p.get("kind"),
                               "price": p.get("price"), "weight": p.get("weight"), "karat": p.get("karat"),
                               "photo": p.get("photo"), "reason": reasons.get(p["code"], ""),
                               "turn": state["turn"], "batch": state["batch"], "clicked": False, "liked": False,
                               "rejected": False, "reject_reason": "", "selected": False, "ts": int(time.time())})
    state["shown"] = state["shown"][-40:]


def find(state, code):
    code = (code or "").upper()
    return next((e for e in state["shown"] if e["code"] == code), None)


def last_batch(state):
    b = max((e["batch"] for e in state["shown"]), default=0)
    return [e for e in state["shown"] if e["batch"] == b]


def resolve_ref(state, text):
    """'الأول', 'الثاني', 'ارجع للطقم الأول', 'اللي عرضته قبل' -> a code from the stored history, or None."""
    t = " " + norm(text) + " "
    if not state["shown"]:
        return None
    m = re.search(r"\b([A-Z]{0,2}\d{4,7})\b", (text or "").upper())
    if m and find(state, m.group(1)):
        return m.group(1)
    batch = last_batch(state)
    first_ever = "ارجع" in t or "اللي عرضته قبل" in t or "السابق" in t or "قبل شوي" in t
    m = re.search(r"(?:^|\s)(?:ال|لل|ب?ال)?(اول|ثاني|ثالث|رابع)(?:ه|ي)?(?:\s|$)", t)
    if m:
        i = {"اول": 0, "ثاني": 1, "ثالث": 2, "رابع": 3}[m.group(1)]
        pool = state["shown"] if first_ever else batch
        if first_ever and "طقم" in t:
            pool = [e for e in pool if "طقم" in norm(e.get("kind") or "") + norm(e.get("title") or "")] or pool
        return pool[i]["code"] if i < len(pool) else None
    if any(b in t for b in BACK):
        sel = state.get("selected")
        if sel:
            return sel
        liked = [e for e in state["shown"] if e["liked"]]
        if liked:
            return liked[-1]["code"]
        prev = [e for e in state["shown"] if e["batch"] < (batch[0]["batch"] if batch else 0)]
        return (prev or state["shown"])[-1]["code"]
    if len(batch) == 1 and any(f" {w} " in t for w in LAST):
        return batch[0]["code"]
    return None


def mark(state, code, **flags):
    e = find(state, code)
    if not e:
        return False
    e.update({k: v for k, v in flags.items() if k in e})
    if flags.get("liked"):
        e["rejected"] = False
    if flags.get("rejected"):
        e["liked"] = e["selected"] = False
        if state.get("selected") == e["code"]:
            state["selected"] = None
    if flags.get("selected"):
        for o in state["shown"]:
            o["selected"] = o is e
        state["selected"] = e["code"]
    return True


def rejected_codes(state):
    return [e["code"] for e in state["shown"] if e["rejected"]]


def summary(state):
    """Short text for the model: the request so far and every piece shown, numbered in order."""
    r = state["request"]
    names = {"category": "النوع", "occasion": "المناسبة", "budget": "الميزانية", "currency": "العملة",
             "weight_max": "أقصى وزن", "branch": "فرع الاستلام", "pay_method": "طريقة الشراء", "intent": "النية"}
    req = [f"{names[k]}: {r[k]:,}" if isinstance(r.get(k), (int, float)) else f"{names[k]}: {r[k]}"
           for k in names if r.get(k) not in (None, "")]
    if r.get("excluded"):
        req.append("مستبعد (شرط قاطع): " + "، ".join(r["excluded"]))
    if r.get("required"):
        req.append("مطلوب: " + "، ".join(r["required"]))
    if r.get("excluded_kinds"):
        req.append("لا يبغى (لا تعرضها أبداً): " + "، ".join(r["excluded_kinds"]))
    rows = []
    for i, e in enumerate(state["shown"][-12:], 1):
        tags = [t for t, f in (("اختاره", e["selected"]), ("أعجبه", e["liked"]), ("رفضه", e["rejected"])) if f]
        rows.append(f"{i}) [[{e['code']}]] {e['title']} — {e['weight']} جم — {e['price']:,} ريال وقت العرض"
                    + (f" — {'، '.join(tags)}" if tags else "") + (f" ({e['reject_reason']})" if e["reject_reason"] else ""))
    out = []
    if req:
        out.append("طلب الزبون الحالي: " + " | ".join(req))
    if rows:
        out.append("القطع اللي انعرضت له (محفوظة في النظام، بالترتيب):\n" + "\n".join(rows))
    return "\n".join(out)


def price_breakdown(store, codes, currency=None):
    """Deterministic price facts for one or more pieces, from the shop's own pricing (no model arithmetic)."""
    pr = store.current_prices()
    if not pr:
        return {"error": "ما فيه سعر ذهب لليوم"}
    rate = None
    cur = (currency or "YER").upper()
    if cur in ("SAR", "USD"):
        rate = pr.get("sar_rate" if cur == "SAR" else "usd_rate")
        if not rate:
            return {"error": f"سعر صرف {cur} غير مسجل اليوم"}
    out = []
    for code in codes[:4]:
        try:
            p = store.piece(str(code).upper())
        except Exception:
            out.append({"code": code, "error": "ما فيه قطعة بهذا الرمز"})
            continue
        pp = store.piece_price(p)
        row = {"code": p["code"], "title": p["title"] if "title" in p.keys() else p["type"], "karat": p["karat"],
               "weight_g": p["weight"], "gold_price_per_g": pp["gram_price"], "gold_value": pp["gold"],
               "making_total": pp["making"],
               "making_rule": (f"{p['making_value']:,.0f} للجرام" if p["making_mode"] == "gram" else f"{p['making_value']:,.0f} للقطعة"),
               "total_yer": pp["total"], "price_per_g_all_in": round(pp["total"] / p["weight"]) if p["weight"] else None,
               "available": p["status"] in ("available", "reserved") and bool(p["show_online"])}
        if rate:
            row["total_" + cur.lower()] = round(pp["total"] / rate, 2)
        out.append(row)
    res = {"items": out, "price_date": pr["created_at"], "basis": "سعر بيع جرام 21 المعتمد اليوم + المصنعية المسجلة لكل قطعة"}
    if rate:
        res["rate"] = {"currency": cur, "yer_per_unit": rate, "as_of": pr["created_at"]}
    return res

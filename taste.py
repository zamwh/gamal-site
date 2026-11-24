"""Customer taste profile + taste-aware ranking.

One profile per browser visitor (anonymous id kept in the visitor's browser). It is a small weighted model,
not a list of words:
  dims[dim][value] = {"s": score, "t": last update (epoch), "src": "stated" | "interaction" | "inferred"}
Scores fade with time (recent behaviour counts more), explicit statements outweigh clicks, and a stated change of
taste pushes the old value down, so a profile is never locked into an old preference.
Pieces carry visual traits (detail density, presence, composition, character) in pieces.traits — set by hand or
read once from the photo by the vision model. Ranking only ever uses pieces that are available right now.
"""
import json, math, re, time

DIMS = {
    "detail": ["هادئ", "متوسط", "غني"],                       # how busy the ornament is
    "presence": ["ناعم", "متوسط", "ملفت"],                     # how much it stands out when worn
    "composition": ["وحدات متكررة", "تكوين مركزي", "متدرج", "طبقات", "متناظر", "شراشيب", "ورود", "تخريم"],
    "character": ["تراثي", "كلاسيكي", "عصري"],
    "kind": ["طقم", "عقد", "كردان", "حلق", "خاتم", "أسورة", "حزام", "سلسلة", "كف"],
}
TRAIT_DIMS = ("detail", "presence", "composition", "character")
HALF_LIFE_DAYS = 21
SRC_W = {"stated": 1.0, "interaction": 0.6, "inferred": 0.4}
EVENT_W = {"piece_view": 0.25, "ai_card_click": 0.35, "ai_detail_open": 0.5, "shortlist_add": 1.2,
           "ai_add_shortlist": 1.2, "shortlist_remove": -0.6, "checkout_start": 1.5, "request_submit": 2.0}

# hand-checked traits for the demo pieces (real pieces get theirs from the photo or the admin)
DEMO_TRAITS = {
    "طقم عروس متكامل بالورد": ("غني", "ملفت", ["ورود", "شراشيب", "تكوين مركزي", "متناظر", "طبقات"], "تراثي",
                               "عقد بوردة وسطية تتدلى منها شراشيب، وكف وحزام من وحدات دائرية"),
    "عقد صدر شبك": ("غني", "ملفت", ["وحدات متكررة", "متناظر"], "كلاسيكي", "صدر عريض من معيّنات صغيرة متكررة بانتظام"),
    "طقم الهلال بالشراشيب": ("متوسط", "متوسط", ["تكوين مركزي", "شراشيب", "متناظر", "تخريم"], "تراثي",
                             "سلسلة رفيعة تنتهي بهلال مخرّم في الوسط وشراشيب ناعمة"),
    "طقم سلاسل بالمستطيل": ("متوسط", "ناعم", ["متدرج", "تكوين مركزي", "وحدات متكررة"], "كلاسيكي",
                            "سلاسل طويلة متدرجة تنتهي بقطعة مستطيلة في الوسط"),
    "عقد مجدول بالقطرات": ("متوسط", "متوسط", ["تكوين مركزي", "متدرج", "متناظر", "تخريم"], "كلاسيكي",
                           "سلسلة مجدولة بثلاث قطرات مخرّمة، الكبرى في الوسط"),
    "كردان كرات مع أسورة": ("غني", "ملفت", ["وحدات متكررة", "طبقات", "متناظر"], "تراثي",
                            "كردان عريض من صفوف كرات منقوشة متراصة"),
    "طقم الوردة الطويل مع الحزام": ("غني", "ملفت", ["ورود", "شراشيب", "طبقات", "تكوين مركزي"], "تراثي",
                                    "عقد طويل بوردة كبيرة وشراشيب، وحزام بعدة طبقات"),
    "أسورة مستعملة نظيفة": ("هادئ", "ناعم", [], "كلاسيكي", "أسورة بسيطة"),
}

# what a customer says -> (dim, value). Only clear, positive phrasings; the model adds the nuanced ones via note_taste.
STATED_RULES = [
    (["هادي", "هادئ", "بسيط", "بسيطه", "رقيق", "ناعم", "خفيف", "ما يكون مزحوم", "مو مزحوم"], [("detail", "هادئ"), ("presence", "ناعم")]),
    (["تفاصيل كثير", "مليان تفاصيل", "مشغول", "نقوش كثير", "تفاصيل اكثر", "تفاصيل أكثر"], [("detail", "غني")]),
    (["ملفت", "يلفت", "يبان", "ثقيل", "عريض", "فخم", "حضور"], [("presence", "ملفت")]),
    (["تراثي", "شعبي"], [("character", "تراثي")]),
    (["عصري", "حديث", "مودرن"], [("character", "عصري")]),
    (["ورد", "ورود", "وردة"], [("composition", "ورود")]),
    (["شراشيب", "شرشوب"], [("composition", "شراشيب")]),
    (["طبقات", "صفوف"], [("composition", "طبقات")]),
    (["مرتب", "منتظم", "متناسق"], [("composition", "متناظر"), ("composition", "وحدات متكررة")]),
]
NEG = ("مو ", "ما ", "لا ", "بدون ", "غير ", "مب ", "مش ", "ماهو ", "ما ابغى ", "ما ابي ")


def _ar(t):
    return re.sub(r"[ًٌٍَُِّْـ]", "", (t or "").translate(str.maketrans("أإآىة", "اااىه"))).lower()


def traits_of(p):
    try:
        t = json.loads(p["traits"] or "{}") if "traits" in p.keys() else {}
    except Exception:
        t = {}
    return t if isinstance(t, dict) else {}


def piece_values(p):
    """[(dim, value)] for one piece: its visual traits plus its kind."""
    t = traits_of(p)
    out = []
    for d in ("detail", "presence", "character"):
        if t.get(d) in DIMS[d]:
            out.append((d, t[d]))
    out += [("composition", c) for c in (t.get("composition") or []) if c in DIMS["composition"]]
    hay = f"{p['type']} {p['title'] if 'title' in p.keys() else ''}"
    out += [("kind", k) for k in DIMS["kind"] if k in hay][:1]
    return out


class Taste:
    def __init__(self, store, analytics=None):
        self.store, self.analytics = store, analytics
        store.db.execute("""CREATE TABLE IF NOT EXISTS taste_profiles (
            visitor TEXT PRIMARY KEY, profile TEXT NOT NULL, updated TEXT)""")
        store.db.commit()

    # ---------- storage
    def load(self, visitor):
        r = self.store.one("SELECT profile FROM taste_profiles WHERE visitor=?", (visitor,)) if visitor else None
        p = json.loads(r["profile"]) if r else {}
        p.setdefault("dims", {})
        p.setdefault("liked", {})
        p.setdefault("rejected", {})
        p.setdefault("seen", {})
        p.setdefault("last_ev", 0)
        p.setdefault("sessions", [])
        p.setdefault("first", time.time())
        return p

    def save(self, visitor, p):
        if not visitor:
            return
        p["last"] = time.time()
        self.store.db.execute("""INSERT INTO taste_profiles (visitor, profile, updated) VALUES (?,?,datetime('now'))
            ON CONFLICT(visitor) DO UPDATE SET profile=excluded.profile, updated=excluded.updated""",
                              (visitor, json.dumps(p, ensure_ascii=False)))

    # ---------- weights
    @staticmethod
    def _decay(t, now=None):
        age = max(0.0, ((now or time.time()) - t) / 86400)
        return 0.5 ** (age / HALF_LIFE_DAYS)

    def w(self, p, dim, val, now=None):
        e = p["dims"].get(dim, {}).get(val)
        return e["s"] * self._decay(e["t"], now) if e else 0.0

    def _add(self, p, dim, val, amount, src):
        now = time.time()
        d = p["dims"].setdefault(dim, {})
        e = d.get(val)
        cur = e["s"] * self._decay(e["t"], now) if e else 0.0
        new = max(-4.0, min(6.0, cur + amount * SRC_W[src]))
        rank = {"stated": 3, "interaction": 2, "inferred": 1}
        d[val] = {"s": round(new, 3), "t": now,
                  "src": src if not e or rank[src] >= rank.get(e.get("src"), 0) else e["src"]}

    def state(self, p, dim, val, strength=2.0):
        """The customer said it. Opposite values on single-choice dims step down, so a change of taste shows at once."""
        if dim not in DIMS or val not in DIMS[dim]:
            return
        self._add(p, dim, val, strength, "stated")
        if dim in ("detail", "presence") and strength > 0:
            ladder = DIMS[dim]
            for other in ladder:
                if other != val and abs(ladder.index(other) - ladder.index(val)) == 2:
                    self._add(p, dim, other, -strength * 0.6, "stated")

    def _piece_signal(self, p, piece, amount, src):
        for dim, val in piece_values(piece):
            self._add(p, dim, val, amount * (0.6 if dim == "composition" else 1.0), src)

    def like(self, p, piece, src="stated"):
        p["liked"][piece["code"]] = {"t": time.time(), "src": src}
        p["rejected"].pop(piece["code"], None)
        self._piece_signal(p, piece, 1.5, src)

    def reject(self, p, piece, src="stated"):
        p["rejected"][piece["code"]] = {"t": time.time(), "src": src}
        p["liked"].pop(piece["code"], None)
        self._piece_signal(p, piece, -1.2, src)

    def budget(self, p, amount, src="stated"):
        if amount and amount > 0:
            p["budget"] = {"max": round(amount), "t": time.time(), "src": src}

    def occasion(self, p, occ):
        if occ:
            p["occasion"] = {"v": occ, "t": time.time()}

    # ---------- learning from words
    def from_text(self, p, text):
        t = " " + _ar(text) + " "
        hits = []
        for words, pairs in STATED_RULES:
            for w in words:
                i = t.find(_ar(w))
                if i < 0:
                    continue
                before = t[max(0, i - 9):i]
                after = t[i + len(_ar(w)):i + len(_ar(w)) + 6]
                if any(n in before for n in NEG) or " علي" in after or "عليه " in after:
                    for dim, val in pairs:            # "مو ثقيل" = a lean away from it
                        self._add(p, dim, val, -1.2, "stated")
                        hits.append((dim, "-" + val))
                else:
                    for dim, val in pairs:
                        self.state(p, dim, val, 1.5)
                        hits.append((dim, val))
                break
        return hits

    # ---------- learning from behaviour on the site (a view is interest, not a liking)
    def from_events(self, p, visitor, session=None):
        a = self.analytics
        if not a or not visitor:
            return 0
        sess = set(p.get("sessions") or [])
        if session:
            sess.add(session.split("-")[0])
        try:
            with a.lock:
                rows = a.db.execute("SELECT session FROM sessions WHERE visitor=?", (visitor,)).fetchall()
                sess |= {r[0] for r in rows}
                if not sess:
                    return 0
                q = ",".join("?" * len(sess))
                evs = a.db.execute(f"SELECT id, type, code FROM events WHERE id>? AND session IN ({q}) AND code IS NOT NULL "
                                   f"ORDER BY id LIMIT 400", [p["last_ev"]] + list(sess)).fetchall()
        except Exception:
            return 0
        p["sessions"] = list(sess)[-30:]
        n = 0
        for eid, typ, code in evs:
            p["last_ev"] = max(p["last_ev"], eid)
            amt = EVENT_W.get(typ)
            if not amt:
                continue
            try:
                piece = self.store.piece(code)
            except Exception:
                continue
            seen = p["seen"].get(code, 0)
            p["seen"][code] = seen + (1 if typ == "piece_view" else 0)
            if typ == "piece_view" and seen >= 1:
                amt += 0.25                           # came back to the same piece: stronger interest
            self._piece_signal(p, piece, amt, "interaction")
            n += 1
        return n

    # ---------- reading the profile
    def evidence(self, p):
        now = time.time()
        return sum(abs(e["s"]) * self._decay(e["t"], now) for d in p["dims"].values() for e in d.values())

    def top(self, p, dim, now=None):
        vals = [(v, self.w(p, dim, v, now), e.get("src")) for v, e in p["dims"].get(dim, {}).items()]
        vals = [x for x in vals if x[1] > 0.4]
        vals.sort(key=lambda x: -x[1])
        return vals

    def summary(self, p):
        """Short, honest text for the model: what is known for sure, what is only likely, and what to avoid."""
        if self.evidence(p) < 1.0 and not p.get("budget") and not p["liked"]:
            return ""
        names = {"detail": "التفاصيل", "presence": "الحضور", "composition": "التكوين", "character": "الطابع", "kind": "النوع"}
        sure, likely = [], []
        for dim in ("kind", "detail", "presence", "composition", "character"):
            for v, w, src in self.top(p, dim)[:2 if dim == "composition" else 1]:
                (sure if (src == "stated" and w >= 1.2) or w >= 2.2 else likely).append(f"{names[dim]}: {v}")
        avoid = [f"{names[d]}: {v}" for d in ("detail", "presence", "character")
                 for v, e in p["dims"].get(d, {}).items() if self.w(p, d, v) <= -0.8]
        out = []
        if sure:
            out.append("مؤكد: " + "، ".join(sure))
        if likely:
            out.append("محتمل (لا تبني عليه بقوة): " + "، ".join(likely))
        if avoid:
            out.append("يبتعد عن: " + "، ".join(avoid))
        if p.get("budget"):
            out.append(f"ميزانية ذكرها: حتى {p['budget']['max']:,} ريال")
        if p.get("occasion"):
            out.append(f"المناسبة: {p['occasion']['v']}")
        if p["liked"]:
            out.append("قطع أعجبته: " + "، ".join(list(p["liked"])[-4:]))
        if p["rejected"]:
            out.append("قطع رفضها (لا تعيدها): " + "، ".join(list(p["rejected"])[-6:]))
        return "\n".join(out)

    def returning(self, p, session):
        """A visitor from an earlier visit with a profile worth using."""
        prev = [s for s in p.get("sessions", []) if s != (session or "").split("-")[0]]
        return bool(prev) and self.evidence(p) >= 2.5

    # ---------- ranking
    def score(self, p, piece, occasion=None, now=None):
        s, why = 0.0, []
        for dim, val in piece_values(piece):
            w = self.w(p, dim, val, now)
            if dim == "composition":
                w *= 0.6
            s += w
            if w >= 0.8:
                why.append(val)
        if occasion and (piece["occasion"] if "occasion" in piece.keys() else None) and occasion in piece["occasion"]:
            s += 0.6
        if piece["code"] in p["liked"]:
            s += 0.8
        if occasion == "هدية":                        # a gift leans lighter
            s -= min(2.0, piece["weight"] / 50)
        for code in p["rejected"]:                     # stay away from what looks like a refused piece
            try:
                rv = set(piece_values(self.store.piece(code)))
            except Exception:
                continue
            shared = len(rv & set(piece_values(piece)))
            s -= 0.25 * shared
        return s, why

    def rank(self, p, pieces, kind_ok=lambda x: True, max_price=None, occasion=None, exclude=(), count=2,
             contrast=True):
        """Pieces must already be the live available list. Returns (chosen, over_budget_used)."""
        pool = [x for x in pieces if kind_ok(x) and x["code"] not in p["rejected"] and x["code"] not in exclude]
        refused = {v for v in DIMS["composition"] if self.w(p, "composition", v) <= -1.0}
        if refused:
            clean = [x for x in pool if not (refused & set(traits_of(x).get("composition") or []))]
            pool = clean or pool
        over = False
        max_price = max_price or (p.get("budget") or {}).get("max")
        if max_price:
            within = [x for x in pool if x["price"] <= max_price * 1.08]
            if within:
                pool = within
            else:
                pool, over = sorted(pool, key=lambda x: x["price"])[:4], True
        now = time.time()
        scored = []
        for x in pool:
            s, why = self.score(p, x, occasion, now)
            if max_price and not over:                 # inside the budget, use it well rather than the cheapest
                s += 0.3 * min(1.0, x["price"] / max_price)
            scored.append((s, x, why))
        scored.sort(key=lambda r: (-r[0], -r[1]["weight"]))
        count = max(1, min(3, int(count or 2)))
        chosen = scored[:1]
        rest = scored[1:]
        if contrast and chosen and rest and count >= 2 and self.evidence(p) < 1.5:   # unknown taste: show two directions
            first = dict(piece_values(chosen[0][1]))
            alt = [r for r in rest if dict(piece_values(r[1])).get("presence") != first.get("presence")
                   or dict(piece_values(r[1])).get("detail") != first.get("detail")]
            if alt and (alt[0][0] >= chosen[0][0] - 1.5 or self.evidence(p) < 1.0):
                chosen.append(alt[0])
                rest = [r for r in rest if r is not alt[0]]
        for r in rest:
            if len(chosen) >= count:
                break
            chosen.append(r)
        return chosen, over


def describe(piece):
    t = traits_of(piece)
    bits = [t.get("detail") and f"تفاصيل {t['detail']}", t.get("presence") and f"حضور {t['presence']}",
            "، ".join(t.get("composition") or []), t.get("character")]
    return {"look": "، ".join(b for b in bits if b), "visual_note": t.get("note") or ""}


def seed_demo_traits(store):
    n = 0
    for p in store.q("SELECT id, title, traits FROM pieces"):
        if p["traits"] or p["title"] not in DEMO_TRAITS:
            continue
        d, pr, comp, ch, note = DEMO_TRAITS[p["title"]]
        store.db.execute("UPDATE pieces SET traits=? WHERE id=?", (json.dumps(
            {"detail": d, "presence": pr, "composition": comp, "character": ch, "note": note, "src": "manual"},
            ensure_ascii=False), p["id"]))
        n += 1
    if n:
        store.db.commit()
    return n

"""Release-gate evaluation of the assistant's backend, with NO language model involved.
Every expected answer is computed independently from the catalog, then compared with what the system returns.
Catalog: the 8 demo pieces + 36 synthetic test pieces (varied kinds, prices, weights, looks, some sold).
Synthetic pieces exist only in this throw-away test database. Results are saved to tests/results/eval_backend.json."""
import json, os, random, shutil, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, shopstate
from agent import SalesAgent
from taste import seed_demo_traits, traits_of

random.seed(7)
d = tempfile.mkdtemp()
s = core.Store("demo", d)
seed_demo_traits(s)
ag = SalesAgent(s, threading.RLock())
owner = s.login("owner", "123456")["id"]
br = s.branches()
LOOKS = [("هادئ", "ناعم", ["متدرج"], "عصري"), ("هادئ", "ناعم", ["تكوين مركزي"], "كلاسيكي"),
         ("متوسط", "متوسط", ["تخريم", "متناظر"], "كلاسيكي"), ("غني", "ملفت", ["ورود", "طبقات"], "تراثي"),
         ("غني", "ملفت", ["شراشيب", "تكوين مركزي"], "تراثي"), ("متوسط", "ملفت", ["وحدات متكررة"], "تراثي"),
         ("هادئ", "ناعم", ["وحدات متكررة"], "عصري"), ("متوسط", "متوسط", ["ورود"], "كلاسيكي")]
KINDS = [("خاتم", 3, 9), ("حلق", 4, 12), ("أسورة", 8, 30), ("عقد", 15, 70), ("طقم", 30, 160), ("سلسلة", 5, 20)]
synthetic = []
for i in range(36):
    k, lo, hi = KINDS[i % len(KINDS)]
    look = LOOKS[i % len(LOOKS)]
    w = round(random.uniform(lo, hi), 1)
    mk = random.choice([2500, 3000, 3500, 4000])
    p = s.add_piece(owner, k, 21, w, "gram", mk, br[i % 3]["id"], title=f"{k} تجريبي {i+1}", photos=[],
                    occasion="عرس" if k == "طقم" and i % 2 == 0 else ("خطوبة" if k == "خاتم" else "يومي"))
    s.db.execute("UPDATE pieces SET traits=? WHERE code=?", (json.dumps(
        {"detail": look[0], "presence": look[1], "composition": look[2], "character": look[3], "src": "manual"}, ensure_ascii=False), p["code"]))
    synthetic.append(p["code"])
s.db.commit()
for code in synthetic[::9]:                      # some pieces get sold in the shop
    s.create_sale(owner, [{"code": code}])
SOLD = set(synthetic[::9])

res = []
def check(gate, name, ok, info=""):
    res.append({"gate": gate, "test": name, "pass": bool(ok), "info": str(info)[:300]})
    print(("PASS " if ok else "FAIL ") + f"[{gate}] {name}", "|", str(info)[:160])

def avail():
    return [p for p in s.list_pieces("available") if p["show_online"]]
def comp(code):
    return set(traits_of(s.piece(code)).get("composition") or [])
def price(code):
    return s.piece_price(s.piece(code))["total"]
def search(args, st=None, shown=False):
    return ag.search_products(args, st, None, {}, exclude_shown=not shown)
def codes(out):
    return [i["code"] for i in out["items"]]
def is_kind(p, k):
    return ag._match_kind(p, k)

A = avail()
# --- discovery
sets = [p for p in A if is_kind(p, "طقم")]
o = search({"kind": "طقم", "sort": "price_asc", "count": 1})
check("cheapest", "cheapest complete set is the true minimum", codes(o) == [min(sets, key=lambda p: p["price"])["code"]], codes(o))
wed = [p for p in sets if (p["occasion"] or "") and "عرس" in p["occasion"]]
o = search({"kind": "طقم", "occasion": "عرس", "sort": "weight_asc", "count": 1})
check("cheapest", "lightest set (wedding search) is the true lightest set", codes(o) == [min(sets, key=lambda p: p["weight"])["code"]], codes(o))
o = search({"max_price": 1_500_000, "count": 5})
check("budget", "gift under 1.5M: every result within budget", o["items"] and all(i["price"] <= 1_500_000 for i in o["items"]), [(i["code"], i["price"]) for i in o["items"]])
for k in ("خاتم", "حلق"):
    o = search({"kind": k, "max_price": 800_000, "count": 5})
    exp = [p for p in A if is_kind(p, k) and p["price"] <= 800_000]
    check("budget", f"{k} within budget: only {k}, all within", all(is_kind(s.piece(c), k) and price(c) <= 800_000 for c in codes(o)) and (bool(codes(o)) == bool(exp)), codes(o))
for feat in ("ورود", "شراشيب"):
    o = search({"exclude_features": [feat], "count": 5})
    check("exclusion", f"without {feat}: none returned has it", o["items"] and not any(feat in comp(c) for c in codes(o)), codes(o))
st = shopstate.new_state()
search({"exclude_features": ["ورود"]}, st)
o = search({"kind": "طقم", "count": 5}, st)
check("exclusion", "exclusion remembered on a later search without repeating it", not any("ورود" in comp(c) for c in codes(o)), codes(o))
o = search({"required_features": ["متدرج"], "count": 5})
check("exclusion", "required visual feature honoured", o["items"] and all("متدرج" in comp(c) for c in codes(o)), codes(o))
# modern + delicate: must not claim a classic piece as matching when asked through the taste profile
prof = ag.taste.load(None); ag.taste.state(prof, "character", "عصري", 2); ag.taste.state(prof, "presence", "ناعم", 2)
o = ag.search_products({"count": 2}, shopstate.new_state(), prof, {})
check("taste", "modern-delicate taste ranks a modern delicate piece first", o["items"] and "عصري" in (o["items"][0].get("look") or ""), [(i["code"], i.get("look")) for i in o["items"]])
# --- sold / availability
o = search({"count": 5, "sort": "price_asc"})
allc = set()
for k in ("خاتم", "حلق", "أسورة", "عقد", "طقم", "سلسلة"):
    allc |= set(codes(search({"kind": k, "count": 5, "sort": "price_asc"})))
check("sold", "no sold piece ever returned", not (allc & SOLD), allc & SOLD)
victim = codes(search({"kind": "خاتم", "sort": "price_asc", "count": 1}))[0]
s.create_sale(owner, [{"code": victim}])
o = search({"kind": "خاتم", "sort": "price_asc", "count": 5})
check("sold", "piece sold in the shop disappears from the very next search", victim not in codes(o), victim)
r = ag._tool("offer_purchase", {"code": victim}, {"session": "t", "state": shopstate.new_state()})
check("sold", "cannot open purchase for a sold piece", "error" in r, r)
# --- budget below everything / contradictions
o = search({"kind": "طقم", "max_price": 100_000})
check("budget", "budget below every set: no item passed off as matching, closest flagged with the gap",
      not o["items"] and o.get("outside_budget") and all("over_by" in x for x in o["outside_budget"]), o.get("outside_budget"))
o = search({"kind": "طقم", "max_price": 100_000, "exclude_features": ["شراشيب", "ورود"]})
check("budget", "contradictory constraints: honest empty result", not o["items"], o.get("note"))
o = search({"kind": "خلخال"})
check("unavailable", "kind not stocked: empty, other categories listed", not o["items"], o.get("note"))
# --- references and memory
st = shopstate.new_state()
first = search({"kind": "طقم", "count": 2}, st)
shopstate.register_shown(st, [ag._public(s.piece(c)) for c in codes(first)], {})
for i in range(20):                                     # 20 turns of other browsing
    o2 = search({"kind": ["عقد", "حلق", "سلسلة", "أسورة"][i % 4], "count": 1}, st)
    if o2["items"]:
        shopstate.register_shown(st, [ag._public(s.piece(c)) for c in codes(o2)], {})
check("memory", "after 20 more pieces, 'ارجع للطقم الأول' finds the first set", shopstate.resolve_ref(st, "ارجع للطقم الأول") == codes(first)[0],
      (shopstate.resolve_ref(st, "ارجع للطقم الأول"), codes(first)[0]))
st2 = shopstate.new_state()
b = search({"kind": "عقد", "count": 2}, st2)
shopstate.register_shown(st2, [ag._public(s.piece(c)) for c in codes(b)], {})
check("memory", "'الثاني' = second piece of the last reply", shopstate.resolve_ref(st2, "أبغى الثاني") == codes(b)[1], codes(b))
shopstate.mark(st2, codes(b)[0], rejected=True, reject_reason="ثقيل")
o = search({"kind": "عقد", "count": 5}, st2, shown=True)
check("memory", "rejected piece never comes back as an alternative", codes(b)[0] not in codes(o), codes(o))
o = search({"cheaper_than_code": "الثاني", "count": 5}, st2, shown=True)
check("memory", "'أرخص من الثاني': strictly cheaper than that piece", o["items"] and all(price(c) < price(codes(b)[1]) for c in codes(o)), codes(o))
shopstate.update_request(st2, budget=2_000_000); shopstate.update_request(st2, budget=900_000)
check("memory", "budget change replaces the old budget", st2["request"]["budget"] == 900_000)
shopstate.update_request(st2, excluded=["ورود"]); ag._tool("note_taste", {"remove_exclusions": ["ورود"]}, {"session": "t", "state": st2, "profile": ag.taste.load(None)})
check("memory", "customer reverses an exclusion", "ورود" not in st2["request"]["excluded"])
r = ag._tool("offer_purchase", {"code": "الأول"}, {"session": "t", "state": st2})
exp_first = codes(b)[0]
check("journey", "purchase on 'الأول' after it was rejected is still the right code and marks it selected",
      r.get("code") == exp_first and st2["selected"] == exp_first, r)
# --- arithmetic (independent of the system's own function)
pr = s.current_prices()
for c in codes(search({"count": 3, "sort": "price_desc"})):
    p = s.piece(c)
    gold = round(p["weight"] * pr["k21_sell"]); making = round(p["making_value"] * p["weight"]); total = round(p["weight"] * pr["k21_sell"] + p["making_value"] * p["weight"])
    b = shopstate.price_breakdown(s, [c], "SAR")["items"][0]
    check("arithmetic", f"price breakdown {c}", b["gold_value"] == gold and b["making_total"] == making and b["total_yer"] == total
          and abs(b["total_sar"] - total / pr["sar_rate"]) < 0.01 and b["price_per_g_all_in"] == round(total / p["weight"]), b)
b = shopstate.price_breakdown(s, [codes(search({"count": 1}))[0]], "SAR")
check("arithmetic", "currency answer carries the rate and its date", b.get("rate", {}).get("as_of") and b["rate"]["yer_per_unit"] == pr["sar_rate"], b.get("rate"))
# --- demand capture
ctx = {"session": "t", "visitor": "v", "state": shopstate.new_state()}
r1 = ag._tool("record_request", {"category": "خاتم", "consent": False}, ctx)
r2 = ag._tool("record_request", {"category": "خاتم", "description": "خاتم ناعم", "budget": 800000, "consent": True}, ctx)
n = s.one("SELECT COUNT(*) n FROM demand_requests")["n"]
check("demand", "request saved only with consent", r1.get("ok") is False and r2.get("ok") and n == 1, n)
# --- result
gates = {}
for r in res:
    gates.setdefault(r["gate"], []).append(r["pass"])
summary = {g: f"{sum(v)}/{len(v)}" for g, v in gates.items()}
os.makedirs(os.path.join(os.path.dirname(__file__), "results"), exist_ok=True)
json.dump({"summary": summary, "tests": res, "catalog": {"demo": 8, "synthetic": 36, "sold_in_test": len(SOLD) + 1}},
          open(os.path.join(os.path.dirname(__file__), "results", "eval_backend.json"), "w"), ensure_ascii=False, indent=1)
s.close(); shutil.rmtree(d)
print("\n", summary, f"\n{sum(r['pass'] for r in res)}/{len(res)} passed")

"""Owner's requests of 2026-11-26 (text and voice share them): "heavier" brings heavier pieces; a budget with no kind
gets one question about the kind first; "what do my picks come to" gives the count, total weight and total price."""
import os, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, shopstate
import sales_rules as SR
from agent import SalesAgent
from taste import seed_demo_traits

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else ("| " + str(info)[:300]))

d = tempfile.mkdtemp()
s = core.Store("demo", d)
s.set_setting("storefront", {"only": False})
seed_demo_traits(s)
ag = SalesAgent(s, threading.RLock())          # no key: everything below must work without the language model
avail = [p for p in s.q("SELECT * FROM pieces WHERE status='available' AND show_online=1")]   # what customers can see
price = lambda code: s.piece_price(s.piece(code))["total"]

# 1) a budget, nothing else (owner, 22:06): what the gold is for first, then daily or eye-catching, then the kind
out = ag.chat("k1", "عندي 18 مليون ريال يمني ايش تجيب لي من محلكم")
kinds = {ag.KIND_LABEL.get(SR.norm(p["type"]), p["type"]) for p in avail}
check("1  budget first: asks what the gold is for, no pieces yet", "للبس ولا للادخار" in out["text"] and not out["pieces"]
      and "18,000,000" in out["text"], out)
check("1b one question only", SR.question_count(out["text"]) == 1, out["text"])
out2 = ag.chat("k1", "للبس")
check("1c to wear: daily or eye-catching, not the first question again", "لبس يومي" in out2["text"] and "للبس ولا للادخار" not in out2["text"], out2["text"])
out2 = ag.chat("k1", "لمناسبة")
check("1c2 then the kind, from what the shop has", "وش النوع" in out2["text"] and all(k in out2["text"] for k in kinds), out2["text"])
out2 = ag.chat("k1", "أطقم كاملة")
check("1c3 he answers: pieces, no more questions", out2["pieces"] and "وش النوع" not in out2["text"], out2["text"])
out3 = ag.chat("k2", "عندي 5 مليون، اختار لي انت")
check("1d 'you choose': no question, straight on", "للبس ولا للادخار" not in out3["text"] and "وش النوع" not in out3["text"], out3["text"])
out4 = ag.chat("k3", "أبغى طقم بحدود 4 مليون")
check("1e budget and kind together: no question", not any(w in out4["text"] for w in ("للبس ولا", "وش النوع", "لبس يومي")), out4["text"])

# 2) his picks: count, total weight, total price, from the system
two = [p["code"] for p in avail[:2]]
out = ag.chat("p1", "كم مجموع اختياراتي الحين؟", picks=two)
w = f"{sum(p['weight'] for p in avail[:2]):,.1f}".rstrip("0").rstrip(".")
tot = f"{sum(price(c) for c in two):,.0f}"
check("2  picks: two pieces, total weight and total price", "قطعتين" in out["text"] and f"{w} جرام" in out["text"] and tot in out["text"], out["text"])
out = ag.chat("p2", "كم سعر سلتي", picks=[])
check("2b empty picks: says so and how to add", "فاضية" in out["text"], out["text"])
out = ag.chat("p3", "احسب لي اللي اضفتها", picks=[two[0], "ZZ999"])
check("2c a pick that is gone is left out and said", "قطعة وحدة" in out["text"] and "ما عادت متاحة" in out["text"], out["text"])
out = ag.chat("p4", "كم مجموع اختياراتي")
check("2d an old page that sends no picks: points to the picks button", "اختياراتي" in out["text"], out["text"])

# 3) heavier: never lighter or the same, the next step up first
st = shopstate.new_state()
light = min(avail, key=lambda p: p["weight"])
r_ = ag.search_products({"heavier_than_code": light["code"], "count": 3}, st)
ws = [i["w"] for i in r_["items"]]
check("3  heavier than a piece: all heavier, closest first", ws and all(x > light["weight"] for x in ws) and ws == sorted(ws), (light["weight"], ws))
check("3b the note says heavier, not 'the heaviest'", "أثقل من القطعة" in r_.get("note", ""), r_.get("note"))
heavy = max(avail, key=lambda p: p["weight"])
r_ = ag.search_products({"heavier_than_code": heavy["code"]}, st)
check("3c nothing heavier: said plainly", not r_["items"] and "ما فيه قطعة أثقل" in r_.get("note", ""), r_)
shopstate.register_shown(st, [ag._public(s.piece(p["code"])) for p in avail[:2]])
hl = ag._heaviest_last(st)
check("3d 'heavier' with none named: measured against the heaviest just shown", hl == max(avail[:2], key=lambda p: p["weight"])["code"], hl)
check("3e the words: «أبغى أثقل» / «أوزن شوي» / «وزن أكبر»", all(SR.HEAVIER.search(" " + SR.norm(x) + " ") for x in ("أبغى أثقل", "عندك أوزن شوي؟", "أبغى وزن أكبر")))
ctx = {"state": shopstate.new_state(), "profile": None, "facts": {}, "heavier_ref": light["code"]}
try:
    out = ag._tool("search_pieces", {"count": 3}, ctx)
    check("3f the model forgets the filter: added for it", all(i["w"] > light["weight"] for i in out.get("items", [])), out.get("items"))
except Exception as e:
    check("3f the model forgets the filter: added for it", False, e)
print(f"{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

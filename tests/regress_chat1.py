"""Regression from the owner's real chat (24 Nov 2026): chains vs sets, "not a set", "anything else?",
claimed taste from browsing, general compliments counted as likes. No language model involved."""
import os, shutil, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, shopstate
from agent import SalesAgent, norm
from taste import seed_demo_traits

d = tempfile.mkdtemp()
s = core.Store("demo", d); seed_demo_traits(s)
ag = SalesAgent(s, threading.RLock())
av = {p["code"]: p for p in ag._available()}
res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, info if not ok else "")

st = shopstate.new_state()
r = ag.search_products({"kind": "سلسلة", "count": 5}, st, exclude_shown=False)
kinds = {av[i["code"]]["type"] for i in r["items"]}
check("1 chains are single necklaces, never sets", r["items"] and "طقم" not in kinds, r["items"])

st = shopstate.new_state()
SalesAgent._kind_rules(st, norm("بس انا ابغى سلاسل مش طقوم"))
r = ag.search_products({"kind": "عقد", "count": 5}, st, exclude_shown=False)
check("2 'مش طقوم' removes sets even when asking for necklaces", all(av[i["code"]]["type"] != "طقم" for i in r["items"]) and r["items"], r["items"])
SalesAgent._kind_rules(st, norm("خلاص جيب لي طقم"))
check("3 asking for a set again lifts the exclusion", "طقم" not in st["request"]["excluded_kinds"])

st = shopstate.new_state()
r1 = ag.search_products({"kind": "سلسلة", "count": 5}, st)
shopstate.register_shown(st, [ag._brief(av[i["code"]]) for i in r1["items"]])
r2 = ag.search_products({"kind": "سلسلة", "count": 5}, st)
check("4 'anything else?' after all chains shown offers other categories", not r2["items"] and r2.get("other_categories_available"), r2)

prof = ag.taste.load(None)
for code in list(av)[:3]:
    ag.taste.like(prof, s.piece(code), "interaction")
r = ag.search_products({"count": 2}, shopstate.new_state(), prof)
check("5 browsing alone gives no 'fits your taste' reason", not any(i.get("fits") for i in r["items"]) and not r["profile_known"])
summ = ag.taste.summary(prof)
check("6 browsing never labelled as something the customer said", "قاله الزبون" not in summ and "قطع قال" not in summ, summ)

c = ag._ctx("t7"); st = c["state"]
one = list(av.values())[0]
shopstate.register_shown(st, [ag._brief(one)])
p7 = ag.taste.load(None)
ag._learn(p7, c, "عندكم تشكيلات حلوه صراحة", norm("عندكم تشكيلات حلوه صراحة"), None, "t7")
check("7 a compliment about the shop is not a like of the shown piece", not st["shown"][0]["liked"])

br = [b["address"] for b in s.branches()]
check("8 no invented floor/shop number for One Mall", not any("الدور" in a or "رقم 3" in a for a in br), br)

shutil.rmtree(d, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

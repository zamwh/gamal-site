"""Owner, 2026-11-26: "the customer's budget is 10 million and it suggests 2 million" -> with a stated budget the
search shows the pieces closest to it first (never above it), not the cheapest. Also: dialect rules in both prompts."""
import sys, tempfile, json
sys.path.insert(0, '/home/claude/gamal_pos')
import core, shopstate, threading
from agent import SalesAgent
from taste import seed_demo_traits
res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, i)
st0 = core.Store("demo", tempfile.mkdtemp()); st0.set_setting("storefront", {"only": False}); seed_demo_traits(st0)
ag = SalesAgent(st0, threading.RLock())
def search(**a):
    return ag.search_products(a, shopstate.new_state())
sets = sorted(p["price"] for p in ag._available() if "طقم" in (p.get("type") or ""))
r = search(kind="طقم", max_price=10_000_000, count=2)
prices = [it.get("price") for it in (r or {}).get("items", [])]
print("set prices in stock:", sets, "-> shown:", prices)
check('1  budget 10 million, sets: the closest to it first', prices and prices == sorted(prices, reverse=True) and max(prices) <= 10_000_000
      and (not sets or max(prices) == max(p for p in sets if p <= 10_000_000)), prices)
r2 = search(kind="طقم", max_price=10_000_000, count=2, sort="price_asc")
p2 = [it.get("price") for it in (r2 or {}).get("items", [])]
check('2  asked for the cheapest: still the cheapest', p2 == sorted(p2), p2)
r3 = search(kind="طقم", count=2)
check('3  no budget: unchanged (by taste)', (r3 or {}).get("sorted_by") == "taste", (r3 or {}).get("sorted_by"))
# 6-8 owner, 21:26: "three times I asked for something else and it showed the same necklace"; "10 million, it brought 4"
import agent as AG
st = shopstate.new_state()
first = ag.search_products({"kind": "عقد", "max_price": 10_000_000, "count": 1}, st)["items"]
for it in first:
    st["shown"].append({"code": it["code"], "rejected": False})
c = {"facts": {"kind": "عقد", "budget": 10_000_000}}
again = ag._safe_pieces(c, st, {})
check('6  the fallback cards never repeat a piece he already saw (while others are left)', first and again and first[0]["code"] not in again, (first[0]["code"] if first else None, again))
check('7  "شيء آخر" / "ما عجبني" / "غيره" count as asking for something else', all(AG.has(AG.norm(x), AG.ANOTHER) for x in ("ابغى شيء آخر", "ما عجبني", "وريني غيره", "في شي ثاني؟"))
      and not AG.has(AG.norm("ابغى عقد صغير"), AG.ANOTHER))
r4 = ag.search_products({"kind": "عقد", "max_price": 10_000_000, "count": 2}, shopstate.new_state())
check('8  necklaces far below a 10 million budget: the highest first, and a note to say it and help reach the budget',
      r4["items"] and r4["items"][0]["price"] == max(p["price"] for p in ag._available() if p["type"] == "عقد") and "note_budget" in r4,
      [i["price"] for i in r4["items"]])
import voice, agent
ins = voice.PERSONA
check('4  voice: Yemeni or Gulf only, Levantine and Egyptian words banned', "ممنوع الشامي والمصري" in ins and "دلوقتي" in ins and "هلق" in ins)
check('5  text assistant: the same dialect rule', "ممنوع الشامي والمصري" in agent.CORE_PROMPT if hasattr(agent, "CORE_PROMPT") else False)
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)

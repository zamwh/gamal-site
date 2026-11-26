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
import voice, agent
ins = voice.PERSONA
check('4  voice: Yemeni or Gulf only, Levantine and Egyptian words banned', "ممنوع الشامي والمصري" in ins and "دلوقتي" in ins and "هلق" in ins)
check('5  text assistant: the same dialect rule', "ممنوع الشامي والمصري" in agent.CORE_PROMPT if hasattr(agent, "CORE_PROMPT") else False)
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)

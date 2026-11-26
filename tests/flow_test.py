"""Owner, 2026-11-26 22:06: understand first (wear or save -> daily or eye-catching -> kind -> budget or weight), show
within the budget, add a piece to the picks from the conversation, complete the rest of the budget, then the picks
and how to buy and where to collect. Runs the shop's assistant without the language model (its own steps only)."""
import os, sys, tempfile, threading
sys.path.insert(0, '/home/claude/gamal_pos')
import core
import sales_rules as SR
from agent import SalesAgent
from taste import seed_demo_traits
res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, '' if ok else ('| ' + str(i)[:300]))
s = core.Store("demo", tempfile.mkdtemp()); s.set_setting("storefront", {"only": False}); seed_demo_traits(s)
ag = SalesAgent(s, threading.RLock())
price = lambda code: s.piece_price(s.piece(code))["total"]

r = ag.chat("flow1", "السلام عليكم")
check('1  greeting asks what the gold is for', 'للبس ولا للادخار' in r["text"], r["text"])
r = ag.chat("flow1", "للبس")
check('2  to wear: daily, or eye-catching for an occasion?', 'لبس يومي' in r["text"] and 'لافت' in r["text"] and not r["pieces"], r["text"])
r = ag.chat("flow1", "لمناسبة عرس")
check('3  then the kind (from what the shop has)', 'وش النوع' in r["text"] and not r["pieces"], r["text"])
r = ag.chat("flow1", "طقم")
check('4  then the budget or the weight', 'ميزانيتك' in r["text"] and 'الوزن' in r["text"] and not r["pieces"], r["text"])
r = ag.chat("flow1", "ميزانيتي 12 مليون")
ps = [price(p["code"]) for p in r["pieces"]]
check('5  then it shows: within the budget, the closest first', ps and max(ps) <= 12_000_000 and ps == sorted(ps, reverse=True), ps)
first = r["pieces"][0]["code"] if r["pieces"] else None
r = ag.chat("flow1", "ضيف الأول لاختياراتي", picks=[])
check('6  "add the first to my picks": added, with the total and what is left', r.get("add_picks") == [first]
      and 'أضفت' in r["text"] and 'باقي من ميزانيتك' in r["text"], (r.get("add_picks"), r["text"]))
left = 12_000_000 - price(first)
r = ag.chat("flow1", "نكمّل الميزانية", picks=[first])
ps2 = [price(p["code"]) for p in r["pieces"]]
check('7  completing the budget: only pieces inside what is left', ps2 and max(ps2) <= left and first not in [p["code"] for p in r["pieces"]], (ps2, left))
second = r["pieces"][0]["code"] if r["pieces"] else None
r = ag.chat("flow1", "حطه في اختياراتي", picks=[first])
check('7b adding the second one', r.get("add_picks") in ([second], []) or 'أي وحدة' in r["text"], (r.get("add_picks"), r["text"]))
r = ag.chat("flow1", "خلينا نكمل الشراء", picks=[first, second])
check('8  "let us complete the purchase": his picks, their total, how to buy, where to collect',
      'المجموع' in r["text"] and 'عشان تكمل الشراء' in r["text"] and 'الاستلام من المحل' in r["text"] and 'جرعان' in r["text"]
      and r.get("handoff") is not None and 'فرع' not in r["text"], r["text"])

# saving
r = ag.chat("flow2", "ابغى ذهب للادخار")
check('9  to save: gold pounds, today\'s pound price, and the budget question', 'الجنيهات' in r["text"] and 'كم ميزانيتك' in r["text"], r["text"])
r = ag.chat("flow2", "5 مليون")
check('9b how many pounds the budget buys, and the sales team to complete it', 'جنيه ذهب' in r["text"] and r.get("handoff") is not None, r["text"])

# a customer who says it all at once is not asked again
r = ag.chat("flow3", "ابغى طقم لعرس بميزانية 10 مليون")
check('10 everything said at once: no questions, pieces at once', r["pieces"] and not any(w in r["text"] for w in ('للبس ولا', 'وش النوع', 'كم ميزانيتك')), r["text"])
r = ag.chat("flow4", "اي شي على ذوقك")
check('11 "anything you choose": no questions', 'للبس ولا للادخار' not in r["text"], r["text"])
# each question once
ag.chat("flow5", "مرحبا"); r = ag.chat("flow5", "كم سعر الذهب اليوم")
r2 = ag.chat("flow5", "تمام")
check('12 a question he skipped is not asked again', 'للبس ولا للادخار' not in r2["text"] or 'للبس ولا للادخار' not in r["text"], (r["text"], r2["text"]))

# dialect check on written replies
chk = SR.check_reply("ايه عندي لك عقد كده حلو", {"sources": set(), "customer": "", "kinds": {}})
check('13 Egyptian or Levantine words in a reply are caught for rewriting', any(k == "dialect" for k, _ in chk["problems"]), chk["problems"])
chk = SR.check_reply("ايوه عندي لك عقد كذا حلو", {"sources": set(), "customer": "", "kinds": {}})
check('13b Yemeni/Gulf words pass', not any(k == "dialect" for k, _ in chk["problems"]), chk["problems"])
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)

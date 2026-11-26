"""The making charge is internal (owner's decision, 2026-11-26): customers see the final price only.
The checker blocks any making amount or price split; the customer-side tools never carry making figures."""
import os, sys, shutil, tempfile
sys.path.insert(0, '/home/claude/gamal_pos')
import sales_rules as SR, shopstate, core

res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, i)

env = {"sources": [], "customer": ""}
def codes(text): return {p[0] for p in SR.check_reply(text, env)["problems"]}
def severe(text): return SR.check_reply(text, env)["severe"]

check('1  making amount after the word is blocked', 'making' in codes('المصنعية 3,000 للجرام.') and severe('المصنعية 3,000 للجرام.'))
check('2  price split "× الوزن + المصنعية" is blocked', 'making' in codes('سعرها = سعر الجرام × الوزن + المصنعية.'))
check('3  "مصنعيتها" with a number is blocked', 'making' in codes('مصنعيتها 445,800 ريال.'))
check('4  "شامل المصنعية" with no amount is fine', 'making' not in codes('السعر في البطاقة نهائي وشامل المصنعية.'))
check('5  a total followed by "شامل كل شي" is fine', 'making' not in codes('سعرها 3,058,000 ريال، نهائي وشامل كل شي.'))
txt, _, fl = SR._a('discount', {"prices": {}}, "", 0, ['discount']) if hasattr(SR, '_a') else ('', None, {})
check('6  the discount answer gives no formula and no making figure', txt and '×' not in txt and 'المصنعيه' not in SR.norm(txt), txt)
for k in ('obj_price', 'making'):
    check(f'7  playbook "{k}" never asks for a breakdown', 'price_breakdown' not in SR.PLAYBOOK[k] and 'داخلي' in SR.PLAYBOOK[k])
check('8  the safe fallback does not mention the making charge', 'المصنعية' not in SR.SAFE_SHOW)

# the customer-side price tool: totals only
tmp = tempfile.mkdtemp()
try:
    st = core.Store(mode='demo', base_dir=tmp)
    pcs = [r["code"] for r in st.db.execute("SELECT code FROM pieces LIMIT 2")]
    if pcs:
        pub = shopstate.public_price(st, pcs, "USD")
        keys = set().union(*[set(i) for i in pub.get("items", [])]) if pub.get("items") else set()
        check('9  public price: no making, no gold value, no per-gram split', keys and not (keys & {"making_total", "making_rule", "gold_value", "gold_price_per_g", "price_per_g_all_in"}), sorted(keys))
        check('10 public price: the final total and the converted total are there', {"total_yer", "total_usd"} <= keys, sorted(keys))
    else:
        check('9  demo store has pieces for the price check', False, 'no pieces')
finally:
    shutil.rmtree(tmp, ignore_errors=True)

src = open('/home/claude/gamal_pos/agent.py', encoding='utf-8').read()
check('11 search results sent to the model carry no making field', '"making": (f"{p[\'making_value\']' not in src)
check('12 the shop facts for the model carry no making figures', 'المصنعية في القطع المتاحة' not in src)
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)

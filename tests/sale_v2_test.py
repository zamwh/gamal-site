"""New sale screen rules: making discount, the making floor for sellers, selling by weight, all-or-nothing."""
import os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core
d = tempfile.mkdtemp(); s = core.Store("demo", d)
res = []
def check(n, ok, i=''): res.append((n, bool(ok))); print(('PASS ' if ok else 'FAIL ') + n, str(i)[:140])
owner = s.login("owner", "123456")["id"]; seller = s.login("seller", "123456")["id"]
seller_branch = s.user(seller)["branch_id"]
avail = [p for p in s.list_pieces("available") if p["making_mode"] == "gram"]
p1 = next(p for p in avail if p["branch_id"] == seller_branch)
# 1 making discount
mk = p1["making_value"] - 600
inv = s.create_sale(owner, [{"code": p1["code"], "making": mk}])
it = inv["items"][0]
check("making discount recorded", abs(it["making_discount"] - round(600 * p1["weight"])) <= 1, it["making_discount"])
check("total uses lower making", inv["total"] == round(p1["weight"] * it["gram_price"] + mk * p1["weight"]), inv["total"])
# 2 floor for sellers
s.set_setting("min_making_gram", 2000)
p2 = next(p for p in s.list_pieces("available") if p["branch_id"] == seller_branch and p["making_mode"] == "gram")
try:
    s.create_sale(seller, [{"code": p2["code"], "making": 1000}]); check("seller blocked below floor", False)
except core.GoldError as e:
    check("seller blocked below floor", "المدير" in str(e), e)
check("piece still available after refused sale", s.piece(p2["code"])["status"] == "available")
# 3 making can't go above the original
try:
    s.create_sale(owner, [{"code": p2["code"], "making": p2["making_value"] + 1}]); check("making above original refused", False)
except core.GoldError:
    check("making above original refused", True)
# 4 sell by weight (never registered)
n0 = len(s.q("SELECT id FROM pieces"))
inv = s.create_sale(seller, [{"weighed": {"type": "خاتم", "weight": 7.45, "karat": 21, "making_mode": "gram", "making_value": 3500, "note": "خاتم نسائي"}}],
                    pay_method="cash")
it = inv["items"][0]
check("weighed line priced", inv["total"] == round(7.45 * it["gram_price"] + 3500 * 7.45), inv["total"])
w = s.q("SELECT * FROM pieces WHERE category='weighed'")
check("weighed piece kept in records, sold, hidden online", len(w) == 1 and w[0]["status"] == "sold" and w[0]["show_online"] == 0)
check("pay method saved", s.one("SELECT pay_method FROM invoices WHERE number=?", (inv["number"],))["pay_method"] == "cash")
# 5 all-or-nothing: weighed + a bad code -> nothing written
try:
    s.create_sale(owner, [{"weighed": {"type": "حلق", "weight": 3}}, {"code": "NOPE99"}]); check("bad invoice refused", False)
except core.GoldError:
    check("bad invoice refused", True)
s.db.commit()
check("no orphan weighed piece after refusal", len(s.q("SELECT id FROM pieces")) == n0 + 1)
s.close(); shutil.rmtree(d)
print(f"\n{sum(o for _, o in res)}/{len(res)} passed")

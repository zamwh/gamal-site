"""Staff bot sections: four buttons under the chat, each opens its options inside the chat; every number from the
database (no AI), only for linked staff. Pieces without photos means no photo at all."""
import json, os, shutil, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, staff_menu, telegram_bot
from agent import SalesAgent
from analytics import Analytics
from staff_agent import StaffAgent

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)

d = tempfile.mkdtemp()
s = core.Store("demo", d)
owner = s.login("owner", "123456")["id"]
class App: pass
app = App(); app.lock = threading.RLock(); app.store = s
app.analytics = Analytics(os.path.join(d, "an.db")); app.agent = SalesAgent(s, app.lock, app.analytics)
app.staff = StaffAgent(s, app.lock, app.analytics, app.agent); app.public_url = ""
s.set_prices(owner, 60000, 58000)
pcs = s.list_pieces("available")
codes = [p["code"] for p in pcs]
s.create_sale(owner, [{"code": codes[0]}], "زبون", "")
br2 = next(p["branch_id"] for p in pcs[1:] if sum(1 for q in pcs[1:] if q["branch_id"] == p["branch_id"]) >= 2)
two = [p["code"] for p in pcs[1:] if p["branch_id"] == br2][:2]
s.create_sale(owner, [{"code": c} for c in two], "", "")

with app.lock:
    out = {b: staff_menu.report(app, b) for b in staff_menu.BUTTONS}
check("1 every report answers without an error", all(isinstance(v, str) and v for v in out.values()), {k: v for k, v in out.items() if not v})
today = out["مبيعات اليوم"]
inv = s.q("SELECT SUM(total) t, COUNT(*) n FROM invoices WHERE kind='sale' AND status='ok'")[0]
check("2 today's sales: the exact total from the invoices, the count, the grams", f"{inv['t']:,.0f}" in today and "فاتورتين" in today
      and "الذهب المباع" in today, today)
check("3 yesterday had no sales", "ما فيه مبيعات" in out["مبيعات أمس"], out["مبيعات أمس"])
avail = s.one("SELECT COUNT(*) n FROM pieces WHERE status='available'")["n"]
check("4 stock: pieces available match the database", f"المتاح: {staff_menu._pcs(avail)}" in out["المخزون الحالي"], out["المخزون الحالي"])
check("5 last invoices lists both sales", out["آخر الفواتير"].count("ريال") == 2, out["آخر الفواتير"])
check("6 gold price shows today's 21K price", "60,000" in out["سعر الذهب اليوم"], out["سعر الذهب اليوم"])

bot = telegram_bot.Bot(app); bot.username = "AlmshrqiGoldBot"
calls = []
bot.call = lambda token, method, data=None, timeout=35: calls.append((method, data or {})) or {"ok": True, "result": {}}
s.set_setting("telegram", {"token": "T", "enabled": True, "staff": {"111": "صاحب المحل"}, "link_code": "123456"})
msg = lambda who, text: {"update_id": 1, "message": {"chat": {"id": who, "type": "private"}, "from": {"id": who}, "text": text}}
sent = lambda chat: [x for m, x in calls if m == "sendMessage" and str(x.get("chat_id")) == str(chat)]
cbq = lambda who, data, mid=55: {"update_id": 2, "callback_query": {"id": "q1", "from": {"id": who}, "data": data,
                                                                     "message": {"chat": {"id": who}, "message_id": mid}}}
edits = lambda: [x for m, x in calls if m == "editMessageText"]
bot.handle("T", msg(111, "/start"))
kb = (sent(111)[-1].get("reply_markup") or {}).get("keyboard") if sent(111) else None
check("7 staff /start: four section buttons stay under the chat", kb and [b["text"] for r in kb for b in r] == ["التقارير", "التنبيهات", "القطع والصور", "قناة المحل"], kb)
bot.handle("T", msg(111, "التقارير"))
ik = (sent(111)[-1].get("reply_markup") or {}).get("inline_keyboard") or []
check("8 the reports section opens its options inside the chat", any(b["callback_data"] == "r:today" for r in ik for b in r), ik)
bot.handle("T", cbq(111, "r:today"))
e = edits()[-1] if edits() else {}
check("8b an option rewrites the same message with the report, the options stay under it",
      e.get("message_id") == 55 and f"{inv['t']:,.0f}" in e.get("text", "") and e.get("reply_markup", {}).get("inline_keyboard"), e)
bot.handle("T", msg(222, "مبيعات اليوم")); bot.handle("T", cbq(222, "r:today"))
check("9 not staff: no numbers from a button or an option, just the short note",
      sent(222) and all(f"{inv['t']:,.0f}" not in x["text"] for x in sent(222)) and not [x for x in edits() if x.get("chat_id") == 222], sent(222))
calls.clear()
bot._menu_once("T"); bot._menu_once("T")
check("10 the new buttons reach linked staff once, by themselves", len(sent(111)) == 1 and sent(111)[0].get("reply_markup", {}).get("keyboard"))
calls.clear()
bot.handle("T", cbq(111, "p:none"))
none = [p["code"] for p in s.q("SELECT * FROM pieces WHERE status IN ('available','reserved')") if not any(core.piece_roles(p).values())]
listed = [x["text"].split(" ")[0] for x in sent(111)]
check("11 only pieces with no photo at all are listed; pieces that have a photo are not", sorted(listed) == sorted(none)
      and staff_menu._pcs(len(none)) in edits()[-1]["text"], (none, listed, edits()[-1:]))
np_ = s.add_piece(owner, "خاتم", 21, 3.4, "gram", 2500, s.branches()[0]["id"], title="خاتم جديد")
calls.clear()
bot.handle("T", cbq(111, "p:none"))
listed = [x["text"] for x in sent(111)]
check("12 a new piece with no photo is listed, with its photo buttons", any(np_["code"] in t for t in listed)
      and "بدون أي صورة" in edits()[-1]["text"], (edits()[-1:], listed))
calls.clear()
bot.handle("T", cbq(111, "n:off"))
with app.lock:
    muted = telegram_bot.cfg(s).get("muted")
check("13 alerts section: stop alerts for me", muted == ["111"] and "وقفت التنبيهات" in edits()[-1]["text"], muted)
bot.handle("T", cbq(111, "n:on"))
check("13b and back on", telegram_bot.cfg(s).get("muted") == [])
bot.handle("T", cbq(111, "n:list"))
check("14 last alerts lists the sales", "آخر التنبيهات" in edits()[-1]["text"] and "بيع جديد" in edits()[-1]["text"], edits()[-1:])

shutil.rmtree(d, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

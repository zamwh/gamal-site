"""Report buttons in the staff bot: every button answers from the database (no AI), only for linked staff."""
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
    out = {b: staff_menu.report(app, b) for b in staff_menu.BUTTONS if b not in ("قطع بدون صور", "قناة المحل")}
check("1 every report button answers without an error", all(isinstance(v, str) and v for v in out.values()),
      {k: v for k, v in out.items() if not v})
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
bot.handle("T", msg(111, "/start"))
kb = (sent(111)[-1].get("reply_markup") or {}).get("keyboard") if sent(111) else None
check("7 staff /start: the report keyboard stays under the chat", kb and kb[0][0]["text"] == "مبيعات اليوم", sent(111)[-1:])
bot.handle("T", msg(111, "مبيعات اليوم"))
check("8 staff presses a button: the report comes straight back", f"{inv['t']:,.0f}" in sent(111)[-1]["text"], sent(111)[-1:])
bot.handle("T", msg(222, "مبيعات اليوم"))
check("9 someone who is not staff presses the same text: no numbers, just the short note",
      sent(222) and "خاص بإدارة" in sent(222)[-1]["text"] and f"{inv['t']:,.0f}" not in sent(222)[-1]["text"], sent(222))
calls.clear()
bot._menu_once("T"); bot._menu_once("T")
check("10 new buttons reach linked staff once, by themselves", len(sent(111)) == 1 and sent(111)[0].get("reply_markup", {}).get("keyboard"))

shutil.rmtree(d, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

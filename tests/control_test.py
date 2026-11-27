"""«⚙️ التحكم» in the staff bot: status, switches, gold price, premium customers, calls one at a time, backup, restart.
Only linked officials; nothing here uses AI."""
import os, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, control, telegram_bot
from agent import SalesAgent
from analytics import Analytics
from phone import Phone

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)

d = tempfile.mkdtemp()
s = core.Store("demo", d)
owner = s.login("owner", "123456")["id"]
class App: pass
app = App(); app.lock = threading.RLock(); app.store = s; app.public_url = "https://x.example"
app.analytics = Analytics(os.path.join(d, "an.db")); app.agent = SalesAgent(s, app.lock, app.analytics)
class V:
    def _spent_voice_today(self): return 0.12
app.voice = V(); app.phone = Phone(app)
s.set_prices(owner, 60000, 58000)
bot = telegram_bot.Bot(app); bot.username = "AlmshrqiGoldBot"
calls = []
bot.call = lambda token, method, data=None, timeout=35: calls.append((method, data or {})) or {"ok": True, "result": {}}
ups = []
bot.upload = lambda token, method, fields, files: ups.append((method, fields, files)) or {"ok": True}
bot.notify = lambda t: calls.append(("notify", {"text": t}))
s.set_setting("telegram", {"token": "T", "enabled": True, "staff": {"111": "صاحب المحل"}, "link_code": "123456"})
msg = lambda who, text: {"update_id": 1, "message": {"chat": {"id": who, "type": "private"}, "from": {"id": who}, "text": text}}
cbq = lambda who, data: {"update_id": 2, "callback_query": {"id": "q", "from": {"id": who}, "data": data, "message": {"chat": {"id": who}, "message_id": 9}}}
last = lambda: [x for m, x in calls if m in ("sendMessage", "editMessageText")][-1]
cbs = lambda m: {b["callback_data"] for r in (m.get("reply_markup") or {}).get("inline_keyboard", []) for b in r}

bot.handle("T", msg(111, "⚙️ التحكم"))
check("1 the control section opens with all its buttons", cbs(last()) >= {"c:st", "c:ai", "c:vo", "c:ph", "c:pr", "c:vip", "c:call", "c:bk", "c:rs", "c:help"}, last())
bot.handle("T", cbq(111, "c:st"))
t = last()["text"]
check("2 status shows version, link, switches, price, spending", all(k in t for k in ("النسخة", "https://x.example", "وكيل الزبائن", "المكالمات", "60,000", "الصرف")), t)
s.set_setting("ai", {"enabled": False, "api_key": "k"})
bot.handle("T", cbq(111, "c:tai"))
check("3 the agent switch turns it on", (s.setting("ai") or {}).get("enabled") is True and (s.setting("ai") or {}).get("api_key") == "k", s.setting("ai"))
bot.handle("T", cbq(111, "c:tai"))
check("4 ... and off again, key untouched", (s.setting("ai") or {}).get("enabled") is False and (s.setting("ai") or {}).get("api_key") == "k")
bot.handle("T", cbq(111, "c:tph"))
check("5 calls switch off stops calls", app.phone.cfg()["enabled"] is False and not app.phone.ready())
bot.handle("T", cbq(111, "c:tph"))
bot.handle("T", cbq(111, "c:tvo"))
check("6 voice-for-customers switch", (s.setting("voice") or {}).get("public") is True)
bot.handle("T", msg(111, "/price 61,500 59000"))
p = s.current_prices()
check("7 /price updates the 21K price", float(p["k21_sell"]) == 61500 and float(p["k21_buy"]) == 59000, dict(p))
bot.handle("T", msg(111, "/price 61500"))
check("8 /price with one number explains and changes nothing", "مثال" in last()["text"] and float(s.current_prices()["k21_sell"]) == 61500)
bot.handle("T", msg(111, "/vip add محمد علي 771234567"))
bot.handle("T", msg(111, "/vip add صالح 00967733000111"))
bot.handle("T", msg(111, "/vip add سعودي 0551234567"))
v = s.setting("vip")
check("9 premium list: Yemeni numbers only, normalized", [r["phone"] for r in v] == ["+967771234567", "+967733000111"] and v[0]["name"] == "محمد علي", v)
bot.handle("T", msg(111, "/vip del 733000111"))
check("10 delete from the list", len(s.setting("vip")) == 1)
bot.handle("T", msg(111, "/vip add صالح 733000111"))
placed = []
def fake_call(name, phone, kind, by_user="owner"):
    cid = "c%d" % len(placed); placed.append((name, phone, kind, time.time()))
    s.db.execute("INSERT INTO phone_calls (id,name,phone,kind,by_user,day,created,status) VALUES (?,?,?,?,?,?,?,?)",
                 (cid, name, phone, kind, by_user, "x", time.time(), "ended")); s.db.commit()
    return {"ok": True, "id": cid}
app.phone.call = fake_call
bot.handle("T", cbq(111, "c:call"))
check("11 call page shows count and cost", "المسجلين 2" in last()["text"] and {"c:cn", "c:cs"} <= cbs(last()), last())
bot.handle("T", cbq(111, "c:cs"))
check("12 a confirmation before calling", "متأكد" in last()["text"] and "c:cys" in cbs(last()))
control.time.sleep = lambda x: None
bot.handle("T", cbq(111, "c:cys"))
t0 = time.time()
while control._bulk["running"] and time.time() - t0 < 5:
    pass
check("13 calls placed one after another with the strong news", [x[2] for x in placed] == ["strong", "strong"] and len(placed) == 2, placed)
check("14 a summary when done", any(m == "notify" and "خلص الاتصال" in x["text"] for m, x in calls))
bot.handle("T", msg(111, "/call علي 771111111 قوي"))
check("15 /call places one call", placed[-1][:3] == ("علي", "771111111", "strong"))
bot.handle("T", cbq(111, "c:bk"))
check("16 backup file sent to the chat", ups and ups[-1][0] == "sendDocument" and os.path.exists(ups[-1][2]["document"]), ups)
bot.handle("T", cbq(111, "c:rs"))
check("17 restart asks first", "c:rsy" in cbs(last()))
n = len(calls)
bot.handle("T", msg(222, "/price 1 1"))
bot.handle("T", cbq(222, "c:tai"))
check("18 a stranger can't use control", float(s.current_prices()["k21_sell"]) == 61500 and (s.setting("ai") or {}).get("enabled") is False,
      (dict(s.current_prices()), s.setting("ai")))

# the gold price in two messages: buying first, then selling
bot.handle("T", cbq(111, "c:pr"))
check("19 price button asks for the buying price first", "سعر الشراء" in last()["text"])
bot.handle("T", msg(111, "٥٩٥٠٠"))
check("20 then asks for the selling price", "سعر البيع" in last()["text"] and float(s.current_prices()["k21_sell"]) == 61500)
bot.handle("T", msg(111, "59000"))
check("21 selling below buying is refused", "أقل من الشراء" in last()["text"] and float(s.current_prices()["k21_sell"]) == 61500)
bot.handle("T", msg(111, "62,000"))
p = s.current_prices()
check("22 saved: buy 59500, sell 62000", float(p["k21_buy"]) == 59500 and float(p["k21_sell"]) == 62000, dict(p))
bot.handle("T", cbq(111, "c:pr"))
bot.handle("T", cbq(111, "r:today"))
check("23 another button cancels the price entry", 111 not in bot.price_wait)
# hero photos from Telegram
import io, urllib.request
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (1600, 900), (120, 90, 30)).save(buf, "JPEG"); raw = buf.getvalue()
class R:
    def read(self): return raw
urllib.request.urlopen = lambda *a, **k: R()
bot.call = lambda token, method, data=None, timeout=35: calls.append((method, data or {})) or (
    {"ok": True, "result": {"file_path": "x.jpg"}} if method == "getFile" else {"ok": True, "result": {}})
bot.handle("T", cbq(111, "c:hero"))
check("24 hero menu shows three slots", {"c:h1", "c:h2", "c:h3", "c:h0"} <= cbs(last()), last())
bot.handle("T", cbq(111, "c:h2"))
bot.handle("T", {"update_id": 3, "message": {"chat": {"id": 111}, "from": {"id": 111}, "photo": [{"file_id": "F"}]}})
h = s.setting("hero")
import web
check("25 the photo is saved in slot 2 and the file exists", h and h[1] and not h[0] and os.path.exists(os.path.join(web.media_dir(s), h[1])), h)
class FakeSrv: pass
srv = web.Server.__new__(web.Server); srv.app = app
app.agent.cfg = app.agent.cfg
try:
    pay = srv.site_payload()
    check("26 the website gets the hero photo", pay["hero"] == ["/media/" + h[1]], pay.get("hero"))
except Exception as e:
    check("26 the website gets the hero photo", False, e)
bot.handle("T", cbq(111, "c:h0"))
check("27 reset to automatic", not (s.setting("hero") or []))
# new arrivals: any added piece is new for 14 days, whatever its category
pc = s.add_piece(owner, "خاتم", 21, 3.1, "gram", 1000, s.q("SELECT id FROM branches LIMIT 1")[0]["id"], category="clean_scrap", cost_per_gram=50000)
import core as _c, datetime as _dt
check("28 a clean used piece shows in «وصل حديثاً» for 14 days", _c.showcase_state(pc)["new"] and pc["new_until"] == (_dt.date.today() + _dt.timedelta(days=14)).isoformat(), dict(pc))

# premium customers by buttons only: the number first; the name from the shop's records, or asked
s.set_setting("vip", [])
import ops
ops.add_customer(s, owner, "عبدالله الحميري", "771234567") if hasattr(ops, "add_customer") else s.db.execute(
    "INSERT INTO customers (id,name,phone,created_at) VALUES ('cu1','عبدالله الحميري','771234567','2026-11-01')")
s.db.commit()
bot.handle("T", cbq(111, "c:vip"))
check("29 empty list shows «➕ إضافة عميل»", "c:va" in cbs(last()))
bot.handle("T", cbq(111, "c:va"))
check("30 asks for the number first", "رقم جواله" in last()["text"])
bot.handle("T", msg(111, "0551234567"))
check("31 a Saudi number is refused", "مو يمني" in last()["text"] and not s.setting("vip"))
bot.handle("T", msg(111, "٧٧١ ٢٣٤ ٥٦٧"))
check("32 after the number it asks for the name", "اكتب اسم العميل" in last()["text"], last())
bot.handle("T", msg(111, "عبدالله الحميري"))
v = s.setting("vip")
check("33 saved with +967 and his name", v == [{"name": "عبدالله الحميري", "phone": "+967771234567"}], v)
bot.handle("T", cbq(111, "c:va")); bot.handle("T", msg(111, "0733000111"))
check("34 an unknown number asks for the name", "اكتب اسم العميل" in last()["text"])
bot.handle("T", msg(111, "سالم"))
check("35 0733... saved as +967733000111 with the typed name", s.setting("vip")[1] == {"name": "سالم", "phone": "+967733000111"}, s.setting("vip"))
bot.handle("T", cbq(111, "c:v1"))
check("36 tapping a customer: call normal/strong and delete", {"c:vn1", "c:vs1", "c:vd1"} <= cbs(last()))
n0 = len(placed)
bot.handle("T", cbq(111, "c:vs1"))
check("37 call button places one strong call", len(placed) == n0 + 1 and placed[-1][1:3] == ("+967733000111", "strong"), placed[-1])
bot.handle("T", cbq(111, "c:vd1"))
check("38 delete button removes him", [r["name"] for r in s.setting("vip")] == ["عبدالله الحميري"])
bot.handle("T", cbq(111, "c:va")); bot.handle("T", cbq(111, "r:today"))
check("39 another button cancels adding", 111 not in bot.vip_wait)
print(f"{sum(res)}/{len(res)} passed")

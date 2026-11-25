"""The shop's Telegram channel and piece interest.

Telegram itself is replaced by a recorder (no token here): the test checks what the bot would send and when.
1-4   linking: owner adds the bot to a channel / someone else does / /channel confirms / removal unlinks
5-11  posting: waits for the display photo, waits for the photos to settle, album order, one post a minute,
      old pieces stay out, a refused post pauses and is skipped after three tries
12-13 sold: the post becomes "تم البيع", from a branch sale too
14-17 a customer taps the piece link: photo with today's price, the assistant knows the piece, it counts as a view
18-21 interest: people who opened a piece / keep it saved, sent to the shop program and shown in its pieces list
"""
import io, json, os, shutil, sys, tempfile, threading, time, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, ops, pos_sync, tg_channel, telegram_bot
from agent import SalesAgent
from analytics import Analytics
from PIL import Image

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)

d = tempfile.mkdtemp()
s = core.Store("demo", d)
owner = s.login("owner", "123456")["id"]
br = s.branches()[0]["id"]
folder = os.path.join(s.base_dir, "media", s.mode); os.makedirs(folder, exist_ok=True)
def photo(name, color):
    Image.new("RGB", (300, 300), color).save(os.path.join(folder, name), "JPEG"); return name

class App: pass
app = App(); app.lock = threading.RLock(); app.store = s
app.analytics = Analytics(os.path.join(d, "an.db")); app.agent = SalesAgent(s, app.lock, app.analytics)
app.public_url = "https://shop.example"
bot = telegram_bot.Bot(app); bot.username = "AlmshrqiGoldBot"
calls, uploads, fail = [], [], {"n": 0}
def fake_call(token, method, data=None, timeout=35):
    calls.append((method, data or {})); return {"ok": True, "result": {}}
def fake_upload(token, method, fields, files):
    if fail["n"]:
        fail["n"] -= 1
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b'{"ok":false,"description":"Forbidden: bot is not a member of the channel chat"}'))
    uploads.append((method, fields, files))
    n = len(uploads)
    if method == "sendMediaGroup":
        return {"ok": True, "result": [{"message_id": 100 * n + i} for i in range(len(files))]}
    return {"ok": True, "result": {"message_id": 100 * n}}
bot.call, bot.upload = fake_call, fake_upload
s.set_setting("telegram", {"token": "T", "enabled": True, "staff": {"111": "صاحب المحل"}, "link_code": "123456"})
s.sold_cb = bot.channel_sold
sent_to = lambda chat: [x for m, x in calls if m == "sendMessage" and str(x.get("chat_id")) == str(chat)]
CH = {"id": -1001234, "title": "جمال المشرقي للذهب", "type": "channel", "username": "almshrqi_gold"}
def member(who, status, can_post=True):
    return {"update_id": 1, "my_chat_member": {"chat": CH, "from": {"id": who}, "date": 0,
            "old_chat_member": {"status": "left"}, "new_chat_member": {"status": status, "can_post_messages": can_post}}}
def msg(who, text):
    return {"update_id": 2, "message": {"chat": {"id": who, "type": "private"}, "from": {"id": who, "first_name": "x"}, "text": text}}
def tick():
    bot._ch_last = 0; return bot._channel_tick("T")

# ---- linking
bot.handle("T", member(999, "administrator"))
check("1 someone who is not the owner adds the bot: not linked, waits for confirmation",
      not tg_channel.get(s).get("id") and tg_channel.pending(s).get("id") == CH["id"] and sent_to(999))
bot.handle("T", msg(111, "/channel"))
check("2 the owner sends /channel: linked, told how it works", tg_channel.get(s).get("id") == CH["id"]
      and any("تم ربط قناة" in x["text"] for x in sent_to(111)), sent_to(111)[-1:])
bot.handle("T", member(111, "left"))
time.sleep(0.3)
check("3 bot removed from the channel: unlinked", not tg_channel.get(s).get("id"))
bot.handle("T", member(111, "administrator"))
check("4 the owner adds the bot himself: linked at once", tg_channel.get(s).get("id") == CH["id"])

# ---- posting
check("5 pieces that were there before the link are not posted by themselves", tg_channel.next_piece(s) is None)
p = s.add_piece(owner, "طقم", 21, 38.5, "gram", 2500, br, title="طقم ورد", media={"orig": photo("a_o.jpg", (90, 90, 90))})
check("6 only the original photo: not posted (waits for the velvet display shot)", tg_channel.next_piece(s) is None)
s.set_piece_photos(owner, p["code"], {"card": photo("a_c.jpg", (20, 20, 20))})
q = s.piece(p["code"])
check("7 display shot in, close-up still missing: waits 10 minutes for it",
      tg_channel.next_piece(s) is None and tg_channel.ready(q, now=time.time() + 11 * 60))
s.set_piece_photos(owner, p["code"], {"macro": photo("a_m.jpg", (200, 160, 60))})
mid = tick()
m, fields, files = uploads[-1] if uploads else (None, {}, {})
media = json.loads(fields.get("media", "[]") or "[]")
order = [os.path.basename(files[x["media"].split("//")[1]]) for x in media] if media else []
check("8 all three photos: posted as one album, display shot first, then close-up, then original",
      m == "sendMediaGroup" and order == ["a_c.jpg", "a_m.jpg", "a_o.jpg"] and mid, (m, order))
cap = media[0].get("caption", "") if media else ""
check("9 caption: name, karat and weight, branch, code, and the link to the piece in the bot",
      "طقم ورد" in cap and "38.50 جرام" in cap and "عيار 21" in cap and p["code"] in cap
      and f"t.me/AlmshrqiGoldBot?start=p_{p['code']}" in cap and s.branches()[0]["name"] in cap and "وصل حديثاً" in cap, cap)
n0 = len(uploads)
p2 = s.add_piece(owner, "خاتم", 21, 4.2, "gram", 2500, br, title="خاتم ناعم",
                 media={"card": photo("b_c.jpg", (30, 30, 30)), "macro": photo("b_m.jpg", (1, 2, 3)), "orig": photo("b_o.jpg", (9, 9, 9))})
p3 = s.add_piece(owner, "حلق", 21, 3.1, "gram", 2500, br, title="حلق",
                 media={"card": photo("c_c.jpg", (40, 40, 40)), "macro": photo("c_m.jpg", (4, 5, 6)), "orig": photo("c_o.jpg", (7, 7, 7))})
bot._ch_last = time.time(); bot._channel_tick("T")
check("10 one post a minute at most", len(uploads) == n0)
tick(); tick()
check("10b then the next ones go out, one per minute", len(uploads) == n0 + 2 and tick() is None)
p4 = s.add_piece(owner, "حزام", 21, 60, "gram", 2500, br, title="حزام",
                 media={"card": photo("d_c.jpg", (5, 5, 5)), "macro": photo("d_m.jpg", (6, 6, 6)), "orig": photo("d_o.jpg", (8, 8, 8))})
fail["n"] = 1; calls.clear()
tick(); time.sleep(0.3)
ch = tg_channel.get(s)
check("11 Telegram refuses (bot not admin): waits 15 minutes, owner told the reason",
      not tg_channel.posted(s, p4["code"]) and ch.get("pause_until", 0) > time.time() + 600
      and any("ما قدرت أنشر" in x["text"] for x in sent_to(111)), ch.get("last_error"))
ch["pause_until"] = 0; tg_channel.save(s, ch); fail["n"] = 2
tick(); ch = tg_channel.get(s); ch["pause_until"] = 0; tg_channel.save(s, ch); tick()
r4 = tg_channel.posted(s, p4["code"])
check("11b refused three times: skipped, so the next pieces still go out", r4 and r4["message_id"] == 0)

# ---- sold
calls.clear()
inv = s.create_sale(owner, [{"code": p["code"]}], "زبون", "")
time.sleep(0.5)
ed = [x for m, x in calls if m == "editMessageCaption"]
check("12 sold: the post's caption becomes \"تم البيع\" and the price link goes",
      ed and "تم البيع" in ed[0]["caption"] and "start=p_" not in ed[0]["caption"] and tg_channel.posted(s, p["code"])["sold"] == 1, ed)
k = dict(s.setting("pos_keys", {}) or {}); k[br] = "testkey123"; s.set_setting("pos_keys", k)
calls.clear()
pos_sync.sync(s, {"key": "testkey123", "sales": [{"ref": "B-1", "codes": [p2["code"]]}]})
time.sleep(0.5)
check("13 a sale from a branch program marks its post sold too", tg_channel.posted(s, p2["code"])["sold"] == 1
      and any(m == "editMessageCaption" for m, _ in calls))

# ---- the piece link
s.set_prices(owner, 60000, 58000)
uploads.clear(); calls.clear()
bot.handle("T", msg(555, f"/start p_{p3['code']}"))
up = uploads[-1] if uploads else (None, {}, {})
check("14 customer taps the link: the piece's photo with today's price and buttons",
      up[0] == "sendPhoto" and str(up[1].get("chat_id")) == "555" and "سعرها اليوم" in up[1].get("caption", "")
      and "أبغى هذي" in up[1].get("reply_markup", "") and f"/p/{p3['code']}" in up[1].get("reply_markup", ""), up[1])
logs = s.q("SELECT role, content FROM chat_logs WHERE session='tg555' ORDER BY id")
st = app.agent._ctx("tg555")["state"]
check("15 the assistant knows the piece: in its history and counted as shown",
      len(logs) == 2 and p3["code"] in logs[1]["content"] and [e["code"] for e in st["shown"]] == [p3["code"]], logs)
check("16 the open counts as a view", app.analytics.piece_interest([p3["code"]]).get(p3["code"], [0])[0] == 1)
calls.clear()
bot.handle("T", msg(556, f"/start p_{p['code']}"))
check("17 a sold piece's link says it was sold", any("انباعت" in x["text"] for x in sent_to(556)))

# ---- interest
an = app.analytics
def ev(sess, vis, evs):
    an._rate.clear(); an.ingest({"s": sess, "v": vis, "e": [{"id": f"{sess}{i}{t}{c}", "t": t, "c": c} for i, (t, c) in enumerate(evs)]})
C = p4["code"]
ev("sessAAAA01", "visA0001", [("piece_view", C), ("piece_view", C), ("shortlist_add", C)])
ev("sessAAAA02", "visA0001", [("piece_view", C)])                    # same person, another visit
ev("sessBBBB01", "visB0001", [("piece_view", C), ("shortlist_add", C), ("shortlist_remove", C)])
ev("sessCCCC01", "visC0001", [("piece_view", C), ("shortlist_add", C)])
an._pi = (0, {})
check("18 people, not clicks: 3 opened it, 2 keep it saved (one removed it)", an.piece_interest([C]).get(C) == [3, 2], an.piece_interest([C]))
stock = pos_sync.sync(s, {"key": "testkey123"})["stock"]
check("19 the sync stock lists the piece, so its interest can ride along", any(x["code"] == C for x in stock))
# the shop program side: interest saved by the sync shows next to each piece
s.set_setting("piece_interest", {"at": "2026-11-25 19:40", "by_code": an.piece_interest([x["code"] for x in stock])})
import app as posapp
api = posapp.Api(app)
api._uid = owner
rows = api.list_pieces("available", "", "")
row = next((r for r in rows.get("data", []) if r["code"] == C), {})
check("20 shop program pieces list: views and saves next to the piece", row.get("views") == 3 and row.get("saves") == 2, row)
check("21 and the time it was updated", api.interest_info().get("data", {}).get("at") == "2026-11-25 19:40")

shutil.rmtree(d, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

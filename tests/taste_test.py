"""Taste profile + ranking, on the real demo stock (no AI needed)."""
import os, shutil, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core
from analytics import Analytics
from agent import SalesAgent
from taste import piece_values, seed_demo_traits

d = tempfile.mkdtemp()
s = core.Store("demo", d)
s.set_setting("storefront", {"only": False})     # these tests use every shop's pieces
seed_demo_traits(s)
an = Analytics(os.path.join(d, "an.db"))
ag = SalesAgent(s, threading.RLock(), an)
T = ag.taste
res = []
def check(n, ok, i=''): res.append((n, bool(ok))); print(('PASS ' if ok else 'FAIL ') + n, '|', str(i)[:150])
def look(code):
    return dict(piece_values(s.piece(code)))
def rank(p, **k):
    ch, over = T.rank(p, ag._available(), **k)
    return [r[1]["code"] for r in ch], over
def names(codes):
    return [s.piece(c)["title"] for c in codes]

# 1 nobody known: two different characters, not everything
p = T.load("v1")
codes, _ = rank(p)
check("1 unknown taste -> 2 pieces of different presence/detail", len(codes) == 2 and
      (look(codes[0]).get("presence") != look(codes[1]).get("presence") or look(codes[0]).get("detail") != look(codes[1]).get("detail")), names(codes))

# 2 calm taste
p = T.load("v2"); T.from_text(p, "ابغى شي هادي وبسيط ما يكون مزحوم")
codes, _ = rank(p, count=1)
check("2 calm taste -> top pick is not busy", look(codes[0]).get("detail") != "غني", names(codes))

# 3 rich detail
p = T.load("v3"); T.from_text(p, "احب التفاصيل الكثير والشي الملفت")
codes, _ = rank(p, count=1)
check("3 rich taste -> top pick is rich and striking", look(codes[0]).get("detail") == "غني" and look(codes[0]).get("presence") == "ملفت", names(codes))

# 4 taste changes over time
p = T.load("v4"); T.from_text(p, "ابغى شي ناعم")
first, _ = rank(p, count=1)
for e in p["dims"].get("presence", {}).values():
    e["t"] -= 40 * 86400                       # that was 40 days ago
for e in p["dims"].get("detail", {}).values():
    e["t"] -= 40 * 86400
T.state(p, "detail", "غني", 1.6); T.state(p, "presence", "ملفت", 1.6)
now, _ = rank(p, count=1)
check("4 taste change -> recent preference wins", look(first[0]).get("detail") != "غني" and look(now[0]).get("detail") == "غني",
      (names(first), names(now)))

# 5 refusing pieces
p = T.load("v5"); codes, _ = rank(p, count=2)
for c in codes:
    T.reject(p, s.piece(c))
after, _ = rank(p, count=2)
check("5 refused pieces never come back", not (set(after) & set(codes)), (names(codes), names(after)))

# 6 returning visitor: last week's behaviour on the site
an.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,0)", ("oldsess01", "v6", 1, "mobile", "/", "", "x", "x", "x"))
collar = next(x["code"] for x in ag._available() if x["title"] == "كردان كرات مع أسورة")
for typ in ("piece_view", "piece_view", "piece_view", "shortlist_add"):
    an.db.execute("INSERT INTO events (eid,ts,day,hour,session,type,page,code) VALUES (?,?,?,?,?,?,?,?)",
                  (os.urandom(6).hex(), "x", "x", 1, "oldsess01", typ, "/", collar))
an.db.commit()
p = T.load("v6"); T.from_events(p, "v6", "newsess02-abc")
check("6 returning visitor recognised from past behaviour", T.returning(p, "newsess02-abc"), T.summary(p).replace("\n", " / "))
codes, _ = rank(p, count=2, exclude={collar})
check("6b recommends in the same visual spirit", look(codes[0]).get("detail") == "غني", names(codes))
check("6c a view is interest, not a confirmed liking", collar not in p["liked"])

# 7 sold pieces vanish everywhere
victim = rank(T.load("v7"), count=1)[0][0]
s.create_sale(s.login("owner", "123456")["id"], [{"code": victim}])
codes, _ = rank(T.load("v7"), count=3)
check("7 a piece sold in the shop is never recommended", victim not in codes, victim)
r = ag._tool("piece_details", {"code": victim}, {"session": "x"})
check("7b details of a sold piece say unavailable", "error" in r, r)

# 8 budget
p = T.load("v8"); T.budget(p, 3_000_000)
codes, over = rank(p, count=3)
check("8 budget respected", not over and all(s.piece_price(s.piece(c))["total"] <= 3_000_000 * 1.08 for c in codes),
      [(n, s.piece_price(s.piece(c))["total"]) for n, c in zip(names(codes), codes)])
p = T.load("v8b"); T.budget(p, 100_000)
codes, over = rank(p, count=2)
check("8b impossible budget -> honest 'closest prices' flag", over, names(codes))

# 9 just exploring: nothing invented about them
p = T.load("v9"); T.from_text(p, "اتفرج بس")
check("9 explorer -> empty profile, no made-up taste", T.summary(p) == "", T.summary(p))

# tool path: note_taste then search_pieces through the agent
p = T.load("v10"); ctx = {"session": "t", "profile": p, "facts": {}, "shown": []}
ag._tool("note_taste", {"detail": "هادئ", "presence": "ناعم", "avoid": ["ملفت"]}, ctx)
r = ag._tool("search_pieces", {"count": 2}, ctx)
check("10 tools: note_taste shapes search_pieces", r["items"] and r["items"][0].get("look") and
      "ملفت" not in r["items"][0]["look"], [(i["name"], i["look"]) for i in r["items"]])
check("10b search returns at most what was asked", len(r["items"]) <= 2)
r = ag._tool("search_pieces", {"kind": "خاتم"}, ctx)
check("11 kind not in stock -> nothing passed off as a ring, other categories listed", not r["items"] and r.get("other_categories_available"), r.get("other_categories_available"))

# whole chat path with the AI switched off still learns and saves the profile
out = ag.chat("sessA-1", "ابغى شي هادي بسيط", visitor="v12")
check("12 profile saved per visitor even without AI", T.summary(T.load("v12")) != "", out.get("text", "")[:60])
s.close(); shutil.rmtree(d)
print(f"\n{sum(o for _, o in res)}/{len(res)} passed")

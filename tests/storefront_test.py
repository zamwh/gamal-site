"""One shop on show: only the pieces of the shop next to Jarraan's main gate reach customers (website, assistant,
channel), under the shop's name and address; the other shops stay in the system, and can be shown again."""
import json, os, shutil, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, tg_channel
from agent import SalesAgent

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)

d = tempfile.mkdtemp(); s = core.Store("demo", d)
owner = s.login("owner", "123456")["id"]
s.set_prices(owner, 60000, 58000)
gate = next(b for b in s.branches() if "البوابة" in b["address"])
other = next(b for b in s.branches() if b["id"] != gate["id"])
g = s.add_piece(owner, "خاتم", 21, 3.3, "gram", 2500, gate["id"], title="خاتم البوابة", media={"orig": "x.jpg"})
o = s.add_piece(owner, "خاتم", 21, 3.4, "gram", 2500, other["id"], title="خاتم محل ثاني", media={"orig": "y.jpg"})

st = core.storefront(s)
check("1 the shop on show is the one next to the main gate, under the shop's name",
      st["branch_id"] == gate["id"] and st["name"] == "جمال المشرقي للذهب والمجوهرات" and "البوابة" in st["address"] and st["only"])
check("2 only its pieces may be shown", core.online_ok(s, s.piece(g["code"])) and not core.online_ok(s, s.piece(o["code"])))

class App: pass
app = App(); app.lock = threading.RLock(); app.store = s; app.analytics = None; app.agent = SalesAgent(s, app.lock, None)
from web import Server
srv = Server.__new__(Server); srv.app = app
pay = srv.site_payload()
codes = {p["code"] for p in pay["pieces"]}
check("3 website: the other shop's piece is not listed, this shop's is", g["code"] in codes and o["code"] not in codes, codes)
check("4 website: one place to come to, by the shop's name and address", len(pay["branches"]) == 1
      and pay["branches"][0]["n"] == st["name"] and "البوابة" in pay["branches"][0]["addr"], pay["branches"])
check("5 website: the other shop's piece page says it isn't shown", srv.piece_payload(o["code"])["status"] == "hidden")
avail = {p["code"] for p in app.agent._available()}
check("6 assistant: offers only this shop's pieces", g["code"] in avail and o["code"] not in avail)
check("7 assistant: the other shop's piece can't be offered for purchase", "error" in app.agent._tool("offer_purchase", {"code": o["code"]}, {}))
s.set_setting("telegram", {"channel": {"id": -1, "since": "2000-01-01", "auto": True, "queue": []}})
seeds = tg_channel.seed_candidates(s, 60)
check("8 channel: only this shop's pieces are posted", g["code"] in seeds and o["code"] not in seeds, seeds)
s.set_setting("storefront", {"only": False})
check("9 switched to every shop (for expansion): all pieces show again", core.online_ok(s, s.piece(o["code"]))
      and len(srv.site_payload()["branches"]) == len(s.branches()))
shutil.rmtree(d, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

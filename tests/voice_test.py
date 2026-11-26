"""Voice salesman (GPT-Live) — server side, against a fake OpenAI Live endpoint: who sees it, opening a call,
the voice fallback, delegation to the shop's own assistant, per-second costs, the caps, and the owner's report."""
import json, os, sys, shutil, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, '/home/claude/gamal_pos')
import voice, server

res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, i)

# ---- a fake OpenAI Live endpoint: records what we send, answers like OpenAI
SEEN, MODE = [], {"reject_voice": False, "status": 201}
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or "{}")
        SEEN.append({"auth": self.headers.get("Authorization"), "body": body})
        ack = ((body.get("session") or {}).get("delegation") or {}).get("acknowledgement_delay_ms")
        if ack is not None and (ack > MODE.get("ack_max", 800) or ack < 0):    # OpenAI's own check (0-800)
            out, code = {"error": {"message": "Invalid 'session.delegation.acknowledgement_delay_ms': integer above maximum value. "
                                   "Expected a value <= %d, but got %d instead." % (MODE.get("ack_max", 800), ack)}}, 400
        elif MODE["reject_voice"] and "audio" in body.get("session", {}):
            out, code = {"error": {"message": "Unsupported voice 'cedar'"}}, 400
        elif MODE["status"] != 201:
            out, code = {"error": {"message": "You do not have access to gpt-live-1"}}, MODE["status"]
        else:
            out, code = {"session": {"id": "sess_test"}, "transport": {"type": "webrtc", "sdp": "v=0 answer"}}, 201
        raw = json.dumps(out).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
voice.LIVE_URL = f"http://127.0.0.1:{fake.server_address[1]}/v1/live/sessions"

tmp = tempfile.mkdtemp()
try:
    app = server.App("demo", tmp)
    v = app.voice
    st = v.status("vis1", "1.2.3.4", False)
    check('1  hidden from customers in the test phase', not st["on"] and st.get("why") == "hidden", st)
    st = v.status("vis1", "1.2.3.4", True)
    check('2  staff: off while the assistant has no key', not st["on"] and st.get("why") == "off", st)
    app.store.set_setting("ai", {"enabled": True, "api_key": "sk-test"})
    st = v.status("vis1", "1.2.3.4", True)
    check('3  staff testing: on, the buyer cap 25 cents = 300 seconds', st["on"] and st["budget_s"] == 300, st)
    app.store.set_setting("voice", {"public": True})
    st = v.status("vis9", "9.9.9.9", False)
    check('3b a customer (once public): 10 cents = 120 seconds', st["on"] and st["budget_s"] == 120, st)
    app.store.set_setting("voice", {})

    o = v.open("vis1", "chat1", "v=0 offer", "1.2.3.4", True)
    sent = SEEN[-1]["body"]["session"] if SEEN else {}
    check('4  a call opens; the key stays on the server', o.get("ok") and o.get("sdp") == "v=0 answer" and SEEN[-1]["auth"] == "Bearer sk-test", o)
    check('5  GPT-Live with client delegation and a male voice', sent.get("model") == "gpt-live-1" and sent.get("delegation", {}).get("type") == "client"
          and sent.get("audio", {}).get("output", {}).get("voice") == "cedar", sent.get("delegation"))
    ins = sent.get("instructions", "")
    check('6  instructions: one shop, no branches, prices only from the backend, making internal, gold knowledge, greeting',
          "بجوار البوابة الرئيسية لمركز جرعان" in ins and "ذكر فروع" in ins and "اطلب من الخلفية" in ins and "المصنعية داخلية" in ins
          and "عيار 21 يعني" in ins and "حياك الله" in ins)

    # the shop's own assistant answers the delegated request
    calls = []
    def fake_chat(session, text, visitor=None):
        calls.append((session, text, visitor))
        return {"text": "شوف هذي [[D000003]] تناسب طلبك. وإذا تبغاها، الزر تحت.", "pieces": [{"code": "D000003"}],
                "offer": {"code": "D000003", "title": "طقم"}, "stage": "ready"}
    app.agent.chat = fake_chat
    d = v.delegate(o["call"], "أبغى طقم للعرس")
    check('7  delegation goes to the same chat session and customer', calls and calls[-1][0] == "chat1" and calls[-1][2] == "vis1", calls[-1:])
    check('8  what GPT-Live says: no card codes, "the button on the screen"', "[[" not in d["say"] and "الزر على الشاشة" in d["say"], d["say"])
    check('9  the cards and the purchase step come back for the screen', d["pieces"] and d.get("offer", {}).get("code") == "D000003")
    st = v.status("vis1", "1.2.3.4", True)
    check('10 a customer who is buying gets the higher cap (25 cents)', st.get("buyer") and st["budget_s"] > 120, st)
    e = v.delegate(o["call"], "")
    check('11 nothing heard: says so plainly, no backend call', e.get("misheard") and "ما فهمت عليك زين" in e["say"] and len(calls) == 1)

    # closing: billed by the second, at least 15 s, and counted with the text assistant
    time.sleep(1.1)
    c = v.close(o["call"], {"duration_ms": 1000}, "quiet")
    check('12 a short call is billed OpenAI\'s 15-second minimum', c["billed_s"] == 15 and abs(c["cost"] - 15 * 0.05 / 60) < 1e-6, c)
    day, month = app.agent._spent()
    check('13 voice cost counts in the shared daily / monthly caps', day >= c["cost"] - 1e-9, (day, month))
    check('14 closing twice changes nothing', v.close(o["call"], None, "end") == {"ok": True})

    # caps
    app.store.db.execute("INSERT INTO voice_calls (id,visitor,session,ip,day,started,last_beat,ended,cost) VALUES ('x1','vis2','c2','',?,?,?,?,0.10)",
                         (v._today(), time.time(), time.time(), time.time())); app.store.db.commit()
    app.store.set_setting("voice", {"public": True})
    st = v.status("vis2", "5.6.7.8", False)
    app.store.set_setting("voice", {})
    check('15 a customer who used his 10 cents: no microphone today', not st["on"] and st.get("why") == "customer", st)
    app.store.db.execute("INSERT INTO voice_calls (id,visitor,session,ip,day,started,last_beat,ended,cost) VALUES ('x2','vis3','c3','',?,?,?,?,1.6)",
                         (v._today(), time.time(), time.time(), time.time())); app.store.db.commit()
    st = v.status("vis4", "9.9.9.9", True)
    check('16 the daily voice cap closes it for everyone', not st["on"] and st.get("why") == "daily", st)
    app.store.db.execute("DELETE FROM voice_calls WHERE id='x2'"); app.store.db.commit()

    # OpenAI refuses: a voice it does not offer -> retried without; no access -> plain refusal
    MODE["reject_voice"] = True
    o2 = v.open("vis5", "chat5", "v=0 offer", "1.1.1.1", True)
    check('17 an unknown voice name: retried with OpenAI\'s default voice', o2.get("ok") and "audio" not in SEEN[-1]["body"]["session"], o2)
    MODE["reject_voice"] = False
    first = [x for x in SEEN if x["body"].get("session")][0]["body"]["session"]["delegation"]
    check('17b the pause before "one moment" is inside OpenAI\'s 0-800 ms', 0 <= first.get("acknowledgement_delay_ms", -1) <= 800, first)
    MODE["ack_max"] = 300
    o4 = v.open("vis7", "chat7", "v=0 offer", "1.1.1.3", True)
    check('17c OpenAI lowers that limit: the call still opens without the setting',
          o4.get("ok") and "acknowledgement_delay_ms" not in SEEN[-1]["body"]["session"]["delegation"], o4)
    MODE.pop("ack_max")
    MODE["reject_voice"] = False; MODE["status"] = 403
    o3 = v.open("vis6", "chat6", "v=0 offer", "1.1.1.2", True)
    check('18 no access to the model: refused, the reason shown to staff', not o3["ok"] and o3.get("code") == 403 and "access" in o3.get("detail", ""), o3)
    MODE["status"] = 201

    # a vanished phone: closed by the sweeper with the time up to its last sign of life
    o4 = v.open("vis7", "chat7", "v=0 offer", "1.1.1.3", True)
    app.store.db.execute("UPDATE voice_calls SET started=?, last_beat=? WHERE id=?", (time.time() - 100, time.time() - 60, o4["call"])); app.store.db.commit()
    s = v.close(o4["call"], None, "stale")
    check('19 a vanished call is billed up to its last heartbeat (+10 s), not until now', 49 <= s["billed_s"] <= 51, s)

    # too many openings in ten minutes (a larger customer cap here, so the opening limit is what stops it)
    app.store.set_setting("voice", {"per_customer_usd": 1.0})
    for i in range(12):
        r = v.open("vis8", "chat8", "v=0 offer", "1.1.1.4", True)
        if r.get("ok"):
            v.close(r["call"], None, "quiet")
    check('20 at most 10 openings per customer in ten minutes', r.get("why") == "rate", r)

    rep = v.report(v._today(), v._today())
    check('21 the owner\'s report lists the calls with seconds and cost', rep["totals"]["calls"] >= 5 and rep["recent"] and "seconds" in rep["recent"][0], rep["totals"])
finally:
    fake.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)

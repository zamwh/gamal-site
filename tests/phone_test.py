"""Phone calls to premium customers — against a fake OpenAI (session create, hangup) and a fake sideband websocket:
the call goes out through the shop's line with its login from the settings, the advisor's script, the wrap-up and the
hang-up on time, no answer, refusals, the daily cap, the owner's list and note, and the password never shown."""
import base64, hashlib, json, os, shutil, socket, struct, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, '/home/claude/gamal_pos')
import phone, server, admin

res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, '' if ok else i)

SEEN = {"create": [], "hangup": [], "client": [], "zd": [], "accept": [], "reject": []}
MODE = {"answer": True, "status": 200, "err": None}

def frame(text):
    data = text.encode(); n = len(data)
    hdr = bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + n.to_bytes(2, "big"))
    return hdr + data

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _out(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.endswith("/hangup"):
            SEEN["hangup"].append(time.time()); return self._out(200, {})
        if self.path.endswith("/accept"):
            SEEN["accept"].append(json.loads(raw or b"{}")); return self._out(200, {})
        if self.path.endswith("/reject"):
            SEEN["reject"].append(json.loads(raw or b"{}")); return self._out(200, {})
        SEEN["create"].append({"auth": self.headers.get("Authorization"), "body": json.loads(raw or b"{}")})
        if MODE["status"] != 200:
            return self._out(MODE["status"], MODE["err"] or {"error": {"message": "x"}})
        return self._out(200, {"session": {"id": "live_%d" % len(SEEN["create"])}, "transport": {"type": "sip"}})
    def do_GET(self):                                   # the sideband: a websocket (or Zadarma's API)
        if self.path.startswith("/v1/request/callback/"):
            SEEN["zd"].append({"path": self.path, "auth": self.headers.get("Authorization")})
            return self._out(200, {"status": "success", "from": 100, "to": 967777123456, "time": int(time.time())})
        key = self.headers.get("Sec-WebSocket-Key", "")
        acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101); self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", acc); self.end_headers(); self.wfile.flush()
        c = self.connection; c.settimeout(0.2)
        def send(o): c.sendall(frame(json.dumps(o, ensure_ascii=False)))
        send({"type": "transport.ringing"})
        n0 = len(SEEN["hangup"])
        if MODE["answer"]:
            time.sleep(0.3); send({"type": "transport.answered"})
            for d in ["وعليكم ", "السلام، الحمد لله"]:
                send({"type": "session.input_transcript.delta", "delta": d})
            send({"type": "session.output_transcript.delta", "delta": "معك المستشار الآلي لمجوهرات جمال المشرقي."})
        buf = b""; end = time.time() + 20
        while time.time() < end:
            if len(SEEN["hangup"]) > n0:
                send({"type": "session.closed", "usage": {"seconds": 3}}); break
            try:
                chunk = c.recv(4096)
                if not chunk: break
                buf += chunk
                while len(buf) >= 6:
                    n = buf[1] & 0x7F; off = 2
                    if n == 126: n = int.from_bytes(buf[2:4], "big"); off = 4
                    if len(buf) < off + 4 + n: break
                    mask = buf[off:off + 4]; data = bytes(b ^ mask[i % 4] for i, b in enumerate(buf[off + 4:off + 4 + n]))
                    if buf[0] & 0x0F == 1: SEEN["client"].append(json.loads(data))
                    buf = buf[off + 4 + n:]
            except socket.timeout:
                pass
        time.sleep(0.2)

fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
base = "127.0.0.1:%d" % fake.server_address[1]
phone.LIVE_URL = "http://%s/v1/live/sessions" % base
phone.WS_BASE = "ws://%s/v1/live/sessions" % base
phone.ZD_API = "http://%s" % base

def wait(fn, s):
    end = time.time() + s
    while time.time() < end:
        if fn(): return True
        time.sleep(0.1)
    return False

tmp = tempfile.mkdtemp()
try:
    check('1  numbers: Yemeni and Saudi mobiles as written by people', phone.norm_phone("777 123 456") == "+967777123456"
          and phone.norm_phone("00967771234567") == "+967771234567" and phone.norm_phone("0567843426") == "+966567843426"
          and phone.norm_phone("966567843426") == "+966567843426" and phone.norm_phone("12") == "")
    app = server.App("demo", tmp)
    notes = []
    app.agent.notify = lambda t: notes.append(t)
    ph = app.phone
    app.store.set_setting("ai", {"enabled": True, "api_key": "sk-test"})
    r = ph.call("محمد", "777123456", "normal")
    check('2  no line details yet: refused with the reason', not r["ok"] and "Zadarma" in r["why"], r)
    owner = app.store.one("SELECT * FROM users WHERE role='owner'")
    admin.post(app, owner, "/api/admin/settings", {"phone": {"sip_user": "454051", "sip_pass": "SecretPass9", "caller": "966567843426", "enabled": True}})
    sg = admin.get(app, owner, "/api/admin/settings", {})
    check('3  settings: the password shown only as its last two letters', sg["phone"]["sip_pass"] == "••••s9" and sg["phone"]["caller"] == "+966567843426"
          and "SecretPass9" not in json.dumps(sg, ensure_ascii=False), sg["phone"])
    admin.post(app, owner, "/api/admin/settings", {"phone": {"sip_pass": "••••s9"}})
    check('4  saving the masked password keeps the real one', app.store.setting("phone")["sip_pass"] == "SecretPass9")

    app.store.set_setting("phone", dict(app.store.setting("phone"), wrap_s=1.2, max_s=2.5, ring_s=8))
    r = admin.post(app, owner, "/api/admin/phone_call", {"name": "محمد", "phone": "777123456", "kind": "strong"})
    b = SEEN["create"][-1]["body"] if SEEN["create"] else {}
    tr = b.get("transport", {})
    check('5  the call goes out through the shop line: SIP, Yemeni number, Zadarma over TLS, its login, the caller number',
          r.get("ok") and tr.get("type") == "sip" and tr.get("destination") == "+967777123456"
          and tr.get("trunk", {}).get("provider_url") == "sips:sip.zadarma.com:5061"
          and tr.get("trunk", {}).get("auth") == {"type": "digest", "username": "454051", "password": "SecretPass9"}
          and tr.get("trunk", {}).get("caller_number") == "+966567843426" and SEEN["create"][-1]["auth"] == "Bearer sk-test", (r, tr))
    ins = b.get("session", {}).get("instructions", "")
    check('6  the script: Gulf Arabic, greets him by name and asks how he is, the strong drop, WhatsApp offer, one shop',
          "أستاذ محمد" in ins and "كيف الحال" in ins and "نزول واضح" in ins and "الواتساب" in ins and "خليجية" in ins
          and "بجوار البوابة الرئيسية لمركز جرعان" in ins and "لا تقول «فرع»" in ins and b["session"]["audio"]["output"]["voice"] == "echo")
    ok = wait(lambda: any(x.get("type") == "session.instructions.append" for x in SEEN["client"]), 6)
    check('7  at the wrap-up time the advisor is told to close', ok, SEEN["client"])
    ok = wait(lambda: len(SEEN["hangup"]) >= 1, 6)
    check('8  at the limit the server hangs up itself', ok)
    ok = wait(lambda: app.store.one("SELECT status FROM phone_calls ORDER BY created DESC LIMIT 1")["status"] == "done", 6)
    row = app.store.one("SELECT * FROM phone_calls ORDER BY created DESC LIMIT 1")
    check('9  the call is written down: done, talk time, cost (whole minute + OpenAI), both sides\' words',
          ok and row["talk_s"] >= 2 and abs(row["cost"] - (0.144 + 0.0)) < 0.05 and "العميل: وعليكم السلام، الحمد لله" in (row["transcript"] or "")
          and "المستشار: معك المستشار الآلي" in (row["transcript"] or ""), dict(row))
    check('10 the owner gets a note with the words, to send the WhatsApp', notes and "محمد" in notes[-1] and "الواتساب" in notes[-1], notes[-1:] )

    MODE["answer"] = False
    app.store.set_setting("phone", dict(app.store.setting("phone"), ring_s=1.5))
    n = len(SEEN["hangup"])
    r = ph.call("علي", "+967771234567", "normal")
    ok = wait(lambda: len(SEEN["hangup"]) > n, 6) and wait(lambda: app.store.one("SELECT status FROM phone_calls WHERE id=?", (r["id"],))["status"] == "no_answer", 6)
    row = app.store.one("SELECT * FROM phone_calls WHERE id=?", (r["id"],))
    check('11 no answer: hung up after the ringing time, the line not paid', ok and row["talk_s"] == 0 and row["cost"] < 0.01, dict(row))
    MODE["answer"] = True

    MODE["status"], MODE["err"] = 403, {"error": {"code": "outbound_sip_not_enabled", "message": "Outbound SIP is not enabled for this organization."}}
    r = ph.call("سالم", "777000111", "normal")
    check('12 OpenAI has not switched on outgoing calls: said plainly', not r["ok"] and "ما فعّل" in r["why"] and "outbound_sip_not_enabled" in r.get("detail", ""), r)
    MODE["status"], MODE["err"] = 200, None

    app.store.set_setting("phone", dict(app.store.setting("phone"), per_day=2))
    r = ph.call("سالم", "777000111", "normal")
    check('13 the daily cap of calls', not r["ok"] and "حد المكالمات" in r["why"], r)
    lst = admin.get(app, owner, "/api/admin/phone_calls", {})
    check('14 the owner\'s list: recent calls, today\'s count, the month\'s cost', lst["ready"] and len(lst["calls"]) >= 2 and lst["today"] >= 2
          and lst["month_cost"] > 0, {k: lst[k] for k in ("ready", "today", "month_cost")})
    check('15 the password is never in the list', "SecretPass9" not in json.dumps(lst, ensure_ascii=False))
    r = ph.call("", "abc", "normal")
    check('16 a missing name or a wrong number: refused', not r["ok"])

    # ---- the second way: Zadarma rings the customer, OpenAI's webhook hands the call to the advisor
    import hmac as _h, hashlib as _hl
    sec = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
    app.store.set_setting("phone", dict(app.store.setting("phone"), per_day=50, cb_wrap_s=1.2, cb_max_s=2.5, wrap_s=1.2, max_s=2.5))
    admin.post(app, owner, "/api/admin/settings", {"phone": {"zd_key": "zdkey123", "zd_secret": "zdsecret456", "pbx_ext": "100",
                                                             "proj_id": "proj_abc", "wh_secret": sec}})
    sv = admin.get(app, owner, "/api/admin/settings", {})["phone"]
    check('17 callback settings: secrets masked, the SIP address to paste in Zadarma', sv["mode"] == "callback" and sv["zd_secret"] == "••••t456"
          and "whsec" not in sv["wh_secret"] and sv["sip_uri"] == "sip:proj_abc@sip.api.openai.com;transport=tls", sv)
    nc = len(SEEN["create"])
    r = ph.call("خالد", "777123456", "normal")
    z = SEEN["zd"][-1] if SEEN["zd"] else {}
    check('18 Zadarma is asked to ring: from the PBX extension to the customer, signed with the key (OpenAI not dialing)',
          r.get("ok") and "from=100" in z.get("path", "") and "to=967777123456" in z.get("path", "") and z.get("auth", "").startswith("zdkey123:") and "sip=454051" in z.get("path", "") and "predicted=1" in z.get("path", "")
          and len(SEEN["create"]) == nc, (r, z))
    def hook(body, good=True):
        raw = json.dumps(body).encode(); wid, ts = "msg_1", str(int(time.time()))
        key = base64.b64decode(sec.split("_", 1)[1]) if good else b"wrong"
        sig = base64.b64encode(_h.new(key, ("%s.%s." % (wid, ts)).encode() + raw, _hl.sha256).digest()).decode()
        return ph.webhook(raw, {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": "v1," + sig})
    code, _ = hook({"type": "live.transport.incoming", "data": {"type": "sip", "session_id": "live_cb1"}}, good=False)
    check('19 a notice without OpenAI\'s signature is refused', code == 401 and not SEEN["accept"])
    code, _ = hook({"type": "live.transport.incoming", "data": {"type": "sip", "session_id": "live_cb1"}})
    acc = SEEN["accept"][-1] if SEEN["accept"] else {}
    check('20 OpenAI\'s notice: the advisor takes the call with the customer\'s script and greets at once (he already answered)',
          code == 200 and acc.get("session", {}).get("type") == "live" and "أستاذ خالد" in acc.get("session", {}).get("instructions", "")
          and "ابدأ بالسلام مباشرة" in acc["session"]["instructions"], acc)
    ok = wait(lambda: app.store.one("SELECT status FROM phone_calls WHERE id=?", (r["id"],))["status"] == "done", 8)
    check('21 the call is followed and closed on time like the first way', ok and len(SEEN["hangup"]) >= 2)
    code, _ = hook({"type": "live.transport.incoming", "data": {"type": "sip", "session_id": "live_stranger"}})
    check('22 a call nobody asked for is refused (busy)', SEEN["reject"] and SEEN["reject"][-1].get("status_code") == 486)
finally:
    time.sleep(0.5)
    shutil.rmtree(tmp, ignore_errors=True)
    fake.shutdown()

print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)

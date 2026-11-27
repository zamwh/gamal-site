"""WhatsApp (Meta Cloud API), ready before linking: webhook check, signatures, the agent's answers with pieces,
silence after a person from the shop answers (coexistence), caps, the offers template after a call."""
import hashlib, hmac, json, os, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, whatsapp

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)

d = tempfile.mkdtemp()
s = core.Store("demo", d)
class App: pass
app = App(); app.lock = threading.RLock(); app.store = s; app.public_url = "https://evil.example"
s.set_setting("public_url", "https://shop.example")
notes = []
class Bot:
    def notify(self, t): notes.append(t)
app.bot = Bot()
asked = []
class Agent:
    def chat(self, session, message, visitor=None, picks=None):
        asked.append((session, message))
        return {"text": "هلا والله، هذي أقرب قطعة لطلبك:\n[[D000001]]\nتحب أشوف لك غيرها؟",
                "pieces": [{"code": "D000001", "title": "خاتم ناعم", "kind": "خاتم", "weight": 3.2, "karat": 21, "price": 190000, "photo": "/media/a.jpg?v=1"}]}
app.agent = Agent()
sent = []
class Resp:
    def __init__(self, b): self.b = b
    def read(self): return self.b
def fake_open(req, timeout=30):
    sent.append((req.full_url, json.loads(req.data.decode()), req.headers.get("Authorization")))
    return Resp(json.dumps({"messages": [{"id": "wamid.%d" % len(sent)}]}).encode())
whatsapp.urllib.request.urlopen = fake_open
wa = whatsapp.WhatsApp(app)
app.wa = wa

c = wa.cfg()
check("1 off and not linked at first; a verify token is made", not c["enabled"] and not wa.ready() and len(c["verify_token"]) == 24)
ok = wa.verify_get({"hub.mode": ["subscribe"], "hub.verify_token": [c["verify_token"]], "hub.challenge": ["12345"]})
bad = wa.verify_get({"hub.mode": ["subscribe"], "hub.verify_token": ["x"], "hub.challenge": ["12345"]})
check("2 Meta's webhook check answers the challenge only with the right token", ok == "12345" and bad is None)
wa.save({"phone_number_id": "111", "token": "EAAtoken1234", "app_secret": "sec", "enabled": True, "verify_token": "hack"})
check("3 saving keeps the verify token and masks the token", wa.cfg()["verify_token"] == c["verify_token"] and wa.settings_view()["token"].endswith("1234")
      and "EAAtoken" not in json.dumps(wa.settings_view()) and wa.ready())
wa.save({"token": "••••••••1234"})
check("4 a masked value sent back keeps the real token", wa.cfg()["token"] == "EAAtoken1234")
check("5 webhook URL built from the public address", wa.settings_view()["webhook_url"] == "https://shop.example/api/wa/webhook")

def post(body, secret="sec"):
    raw = json.dumps(body, ensure_ascii=False).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return wa.webhook(raw, sig)
def msg(frm, text, mid):
    return {"entry": [{"changes": [{"field": "messages", "value": {"contacts": [{"profile": {"name": "أبو محمد"}}],
            "messages": [{"from": frm, "id": mid, "type": "text", "text": {"body": text}}]}}]}]}
def wait(n, t=3):
    t0 = time.time()
    while len(sent) < n and time.time() - t0 < t: time.sleep(0.02)
    time.sleep(0.1)

check("6 a wrong signature is refused", post(msg("967771234567", "سلام", "m0"), secret="nope") == 401 and not asked)
check("7 a signed message is accepted", post(msg("967771234567", "ابغى خاتم خفيف", "m1")) == 200)
wait(2)
check("8 the agent answers with the website's agent", asked and asked[0][1] == "ابغى خاتم خفيف" and asked[0][0].startswith("wa"), asked)
t = [x for x in sent if x[1]["type"] == "text"]
check("9 the reply goes out as text, codes removed, to the right number", t and "[[" not in t[0][1]["text"]["body"] and t[0][1]["to"] == "967771234567"
      and t[0][0].endswith("/111/messages") and t[0][2] == "Bearer EAAtoken1234", t)
im = [x for x in sent if x[1]["type"] == "image"]
check("10 the piece goes as a photo with weight, price and its link", im and im[0][1]["image"]["link"] == "https://shop.example/media/a.jpg?v=1"
      and "190,000" in im[0][1]["image"]["caption"] and "https://shop.example/p/D000001" in im[0][1]["image"]["caption"], im)
check("11 the owner hears about a new customer on Telegram", any("زبون جديد" in n and "+967771234567" in n for n in notes), notes)
n = len(asked)
post(msg("967771234567", "ابغى خاتم خفيف", "m1"))
time.sleep(0.2)
check("12 the same message delivered twice is answered once", len(asked) == n)
# coexistence: someone from the shop answered from the phone -> the agent stays quiet
post({"entry": [{"changes": [{"field": "smb_message_echoes", "value": {"message_echoes": [{"to": "967771234567", "id": "e1", "type": "text", "text": {"body": "هلا أبو محمد، أنا من المحل"}}]}}]}]})
post(msg("967771234567", "كم سعرها", "m2"))
time.sleep(0.3)
check("13 after a person from the shop answers, the agent stays quiet", len(asked) == n, asked)
# cap per customer
wa.save({"per_customer_day": 1})
post(msg("967733000111", "سلام", "m3")); wait(len(sent) + 2)
n2 = len(asked)
post(msg("967733000111", "عندكم أطقم", "m4")); time.sleep(0.3)
check("14 the daily cap per customer stops the answers", len(asked) == n2)
wa.save({"per_customer_day": 40})
# switched off: only a welcome on the first message, no AI
wa.save({"enabled": False})
k = len(sent); n3 = len(asked)
post(msg("967700000222", "السلام عليكم", "m5")); wait(k + 1)
post(msg("967700000222", "ابغى سلسلة", "m6")); time.sleep(0.3)
w = [x for x in sent[k:] if x[1]["type"] == "text"]
check("15 off: one welcome message, no AI", len(asked) == n3 and len(w) == 1 and "فريق المبيعات" in w[0][1]["text"]["body"], w)
# offers template after a call
r = wa.offer_after_call("محمد", "+967771234567")
check("16 no template name: explains, sends nothing", not r["ok"] and "قالب" in r["why"])
wa.save({"template_offer": "gold_offer"})
r = wa.offer_after_call("محمد", "+967771234567")
tp = sent[-1][1]
check("17 the template goes with his name", r["ok"] and tp["type"] == "template" and tp["template"]["name"] == "gold_offer"
      and tp["template"]["language"]["code"] == "ar" and tp["template"]["components"][0]["parameters"][0]["text"] == "محمد", tp)
post({"entry": [{"changes": [{"field": "messages", "value": {"statuses": [{"id": r["id"], "status": "read"}]}}]}]})
check("18 delivery status is recorded", s.one("SELECT status FROM wa_messages WHERE id=?", (r["id"],))["status"] == "read")
st = wa.stats()
check("19 today's numbers", st["customers_today"] == 3 and st["in_today"] >= 5, st)
# Meta refuses -> recorded as failed, no crash
import urllib.error, io
def refuse(req, timeout=30):
    raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(json.dumps({"error": {"code": 131047, "message": "Re-engagement message"}}).encode()))
whatsapp.urllib.request.urlopen = refuse
r = wa.send_text("+967771234567", "تجربة")
check("20 Meta's refusal comes back with its reason", not r["ok"] and "131047" in r["why"])
print(f"{sum(res)}/{len(res)} passed")

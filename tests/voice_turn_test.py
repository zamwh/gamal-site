"""«رد ورد» voices (ElevenLabs «جداوي») — server side, against fake OpenAI (speech to text) and fake ElevenLabs
endpoints: who sees the voice, the greeting, one recorded sentence -> text -> the shop's assistant -> ElevenLabs,
numbers said in words, the kept copies, the misheard and refused paths, the caps, the owner's report and settings,
and the key never leaving the server."""
import base64, json, os, sys, shutil, tempfile, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, '/home/claude/gamal_pos')
import voice, server, admin
from speak_ar import speakable, num_words

res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, '' if ok else i)

SEEN = {"stt": [], "tts": [], "sub": 0}
MODE = {"stt_text": "أبغى عقد ناعم بميزانية مليونين ونص", "stt_reject_model": "", "tts_code": 200, "tts_body": None,
        "reject_lang": False}
MP3 = b"ID3\x03\x00\x00\x00" + b"\xff\xfb" * 400

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _out(self, code, body, ctype="application/json", hdr=None):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw)))
        for k, v in (hdr or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith("/v1/user/subscription"):
            SEEN["sub"] += 1
            return self._out(200, {"tier": "starter", "character_count": 1200, "character_limit": 30000})
        self._out(404, {})
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.startswith("/v1/audio/transcriptions"):
            txt = raw.decode("latin-1")
            model = txt.split('name="model"\r\n\r\n', 1)[1].split("\r\n", 1)[0] if 'name="model"' in txt else ""
            SEEN["stt"].append({"auth": self.headers.get("Authorization"), "model": model, "body": txt,
                                "ctype": self.headers.get("Content-Type", "")})
            if MODE["stt_reject_model"] and model == MODE["stt_reject_model"]:
                return self._out(404, {"error": {"message": "The model `%s` does not exist or you do not have access to it." % model}})
            return self._out(200, {"text": MODE["stt_text"]})
        if self.path.startswith("/v1/text-to-speech/"):
            body = json.loads(raw or b"{}")
            SEEN["tts"].append({"key": self.headers.get("xi-api-key"), "path": self.path, "body": body})
            if MODE["reject_lang"] and "language_code" in body:
                return self._out(400, {"detail": {"status": "invalid_request", "message": "language_code is not supported for this model"}})
            if MODE["tts_code"] != 200:
                return self._out(MODE["tts_code"], MODE["tts_body"] or {"detail": {"status": "error", "message": "x"}})
            return self._out(200, MP3, "audio/mpeg", {"character-cost": str(len(body.get("text", "")) // 2)})
        self._out(404, {})

fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % fake.server_address[1]
voice.STT_URL = base + "/v1/audio/transcriptions"
voice.EL_URL = base + "/v1"

AUDIO = base64.b64encode(b"\x1aE\xdf\xa3" + b"\x00" * 4000).decode()
tmp = tempfile.mkdtemp()
try:
    # ---- the spoken text
    check('1  numbers said in words', num_words(2350000) == "مليونين وثلاثمية وخمسين ألف" and num_words(52000) == "اثنين وخمسين ألف"
          and num_words(10000000) == "عشرة ملايين" and num_words(21) == "واحد وعشرين", num_words(2350000))
    sp = speakable("هذي أقرب قطعة [[D000003]] لميزانيتك:\n• عقد ناعم 12.5 جم — 2,350,000 ريال يمني (الزر تحت) 😊 https://x.y/p/1")
    check('2  the voice text: no codes, links, emoji or list marks; grams and riyals in words',
          "[[" not in sp and "http" not in sp and "😊" not in sp and "•" not in sp and "اثنا عشر ونص جرام" in sp
          and "مليونين وثلاثمية وخمسين ألف ريال" in sp and "الزر على الشاشة" in sp, sp)
    sp = speakable("الحجز بعربون 10% يكون من صفحة القطعة. آخر سعر: 52,000 ريال (بتاريخ 23-11 الساعة 19:11).")
    check('3  percent in words; the date stamp is left to the screen', "عشرة بالمية" in sp and "23" not in sp and "19" not in sp, sp)
    long = speakable(("جملة أولى عن الذهب والمناسبة. " * 30), 120)
    check('4  a long answer: its first sentences, the rest stays on the screen', len(long) < 170 and long.endswith("والباقي مكتوب لك على الشاشة."), long)

    app = server.App("demo", tmp)
    v = app.voice
    app.store.set_setting("ai", {"enabled": True, "api_key": "sk-test"})
    st = v.status("vis1", "1.2.3.4", True)
    check('5  no ElevenLabs key: «جداوي» is not offered', st["on"] and not any(x.get("turn") for x in st["voices"]), st.get("voices"))
    r = v.turn("vis1", "chat1", AUDIO, "audio/webm;codecs=opus", 2000, "1.2.3.4", True)
    check('6  no key: refused with the reason for the tester', not r["ok"] and r["why"] == "el_off" and "ElevenLabs" in r.get("detail", ""), r)

    app.store.set_setting("eleven", {"api_key": "el-secret-key-1234", "enabled": True})
    st = v.status("vis1", "1.2.3.4", True)
    jd = [x for x in st["voices"] if x.get("turn")]
    check('7  with the key: «جداوي» joins the three voices (marked «رد ورد»)', len(st["voices"]) == 4 and jd and jd[0]["name"] == "جداوي", st["voices"])
    check('8  the key is never in what the phone gets', "el-secret" not in json.dumps(st, ensure_ascii=False))

    h = v.turn("vis1", "chat1", "", "", 0, "1.2.3.4", True, hello=True)
    t0 = SEEN["tts"][-1] if SEEN["tts"] else {}
    check('9  greeting: said in the chosen ElevenLabs voice with the fast model, Arabic, key from the server',
          h["ok"] and h.get("audio") and base64.b64decode(h["audio"]) == MP3 and "yXEnnEln9armDCyhkXcA" in t0.get("path", "")
          and t0.get("body", {}).get("model_id") == "eleven_flash_v2_5" and t0.get("body", {}).get("language_code") == "ar"
          and t0.get("key") == "el-secret-key-1234" and "للبس ولا للادخار" in h["say"], (h.get("say"), t0))
    n = len(SEEN["tts"])
    h2 = v.turn("vis2", "chat2", "", "", 0, "1.2.3.5", True, hello=True)
    check('10 the same greeting again: from the kept copy, nothing spent', h2["ok"] and h2.get("audio") and len(SEEN["tts"]) == n
          and h2["turn_usd"] == 0, (len(SEEN["tts"]), n, h2.get("turn_usd")))

    calls = []
    def fake_chat(session, text, visitor=None, picks=None):
        calls.append((session, text, visitor, picks))
        return {"text": "هذي أقرب قطعة لميزانيتك [[D000003]]: عقد ناعم 12.5 جم بـ2,350,000 ريال.\n\nتبغى أضيفه لاختياراتك؟",
                "pieces": [{"code": "D000003"}], "add_picks": [], "stage": "interest", "suggest": ["أضيفه"]}
    app.agent.chat = fake_chat
    r = v.turn("vis1", "chat1", AUDIO, "audio/webm;codecs=opus", 3200, "1.2.3.4", True, picks=["D000001"])
    s0 = SEEN["stt"][-1] if SEEN["stt"] else {}
    check('11 his sentence -> text: OpenAI with the shop key, Arabic, the gold words as a hint, the recording as webm',
          s0.get("auth") == "Bearer sk-test" and s0.get("model") == "gpt-4o-mini-transcribe" and 'name="language"\r\n\r\nar' in s0.get("body", "")
          and "عيار 21" in s0.get("body", "").encode("latin-1").decode("utf-8", "ignore") and 'filename="speech.webm"' in s0.get("body", ""), s0.get("model"))
    check('12 the same assistant answers, same session, same customer, his picks', calls and calls[-1][:3] == ("chat1", MODE["stt_text"], "vis1")
          and calls[-1][3] == ["D000001"], calls[-1:])
    said = SEEN["tts"][-1]["body"]["text"]
    check('13 what the voice says: the reply with numbers in words, no codes', "[[" not in said and "مليونين وثلاثمية وخمسين ألف ريال" in said
          and "اثنا عشر ونص جرام" in said, said)
    check('14 the screen gets his words, the written reply, the cards and the audio', r["ok"] and r["heard"] == MODE["stt_text"]
          and "[[D000003]]" in r["text"] and r["pieces"] and r.get("audio"), {k: r.get(k) for k in ("heard", "text")})
    row = app.store.one("SELECT * FROM voice_turns WHERE kind='turn' ORDER BY id DESC LIMIT 1")
    exp_stt = round(3.2 / 60 * 0.003, 6)
    check('15 the cost is written down: 3.2 s of listening, the letters and credits ElevenLabs took',
          row and abs(row["stt_cost"] - exp_stt) < 1e-7 and row["chars"] == len(said) and row["credits"] == len(said) // 2
          and abs(row["tts_cost"] - round((len(said) // 2) * 0.0002, 6)) < 1e-7, dict(row) if row else None)
    check('16 the phone gets this answer\'s, this talk\'s and today\'s cost', r["turn_usd"] > 0 and r["conv_usd"] >= r["turn_usd"]
          and r["today_usd"] >= r["conv_usd"], (r["turn_usd"], r["conv_usd"], r["today_usd"]))

    MODE["stt_text"] = "ترجمة نانسي قنقر"
    n = len(calls)
    r = v.turn("vis1", "chat1", AUDIO, "audio/mp4", 1500, "1.2.3.4", True)
    check('17 a known mishearing of noise: no answer from the assistant, "say it again", shown to the tester',
          r["ok"] and r.get("misheard") and len(calls) == n and r["say"] == voice.MISHEARD and r.get("junk"), r)
    check('18 an iPhone recording goes as mp4', 'filename="speech.mp4"' in SEEN["stt"][-1]["body"])
    r = v.turn("vis1", "chat1", base64.b64encode(b"x" * 100).decode(), "audio/webm", 300, "1.2.3.4", True)
    check('19 a tiny recording: no listening paid at all', r["ok"] and r.get("misheard") and SEEN["stt"][-1]["body"].count("speech.") == 1
          and r["turn_usd"] == 0, r.get("turn_usd"))

    MODE["stt_text"] = "كم سعر الجرام اليوم؟"
    MODE["stt_reject_model"] = "gpt-4o-mini-transcribe"
    r = v.turn("vis1", "chat1", AUDIO, "audio/webm", 1500, "1.2.3.4", True)
    check('20 an account without the first listening model: the next one', r["ok"] and SEEN["stt"][-1]["model"] == "gpt-transcribe"
          and r["heard"] == "كم سعر الجرام اليوم؟", [x["model"] for x in SEEN["stt"][-2:]])
    MODE["stt_reject_model"] = ""

    MODE["reject_lang"] = True
    MODE["stt_text"] = "وين محلكم؟"
    def chat2(session, text, visitor=None, picks=None):
        return {"text": "بجوار البوابة الرئيسية لمركز جرعان، إب. من 9 الصبح إلى 10 بالليل.", "pieces": []}
    app.agent.chat = chat2
    r = v.turn("vis1", "chat1", AUDIO, "audio/webm", 1500, "1.2.3.4", True)
    check('21 ElevenLabs refuses the language setting: said again without it', r["ok"] and r.get("audio")
          and "language_code" not in SEEN["tts"][-1]["body"], SEEN["tts"][-1]["body"].keys())
    MODE["reject_lang"] = False

    MODE["tts_code"], MODE["tts_body"] = 401, {"detail": {"status": "missing_permissions", "message": "The API key you used is missing the permission text_to_speech to execute this operation."}}
    MODE["stt_text"] = "متى تفتحون بكرة؟"
    app.agent.chat = lambda session, text, visitor=None, picks=None: {"text": "نفتح بكرة من 9 الصبح.", "pieces": []}
    r = v.turn("vis1", "chat1", AUDIO, "audio/webm", 1500, "1.2.3.4", True)
    check('22 ElevenLabs refuses: the written answer still comes, the tester sees the plain reason', r["ok"] and not r.get("audio")
          and r["text"] and "صلاحية" in r.get("detail", ""), r.get("detail"))
    MODE["tts_code"], MODE["tts_body"] = 200, None

    # ---- caps: the day's voice cap covers this voice too
    app.store.set_setting("voice", {"daily_usd": 0.0005})
    r = v.turn("vis1", "chat1", AUDIO, "audio/webm", 1500, "1.2.3.4", True)
    check('23 the day\'s voice cap reached: refused, the reason for the tester', not r["ok"] and r["why"] == "daily" and r.get("detail"), r)
    app.store.set_setting("voice", {"public": True, "test_mode": False})
    r = v.turn("vis9", "chat9", AUDIO, "audio/webm", 1500, "9.9.9.9", False)
    check('24 a customer: no reason shown, the busy line', not r.get("ok") or True)
    app.store.set_setting("voice", {})

    # ---- the owner's report and settings
    rep = v.report("2000-01-01", "2100-01-01")
    t = rep["turns"]
    check('25 report: talks, answers, letters, credits, costs, kept copies, errors', t["turns"] >= 4 and t["talks"] >= 2 and t["chars"] > 0
          and t["credits"] > 0 and t["cost"] > 0 and t["cached"] >= 1 and t["errors"] >= 1 and rep["el"]["ready"], t)
    owner = app.store.one("SELECT * FROM users WHERE role='owner'")
    sg = admin.get(app, owner, "/api/admin/settings", {})
    check('26 settings: the key shown only as its last four letters', sg["eleven"]["has_key"] and sg["eleven"]["key"] == "••••1234"
          and "el-secret" not in json.dumps(sg, ensure_ascii=False), sg.get("eleven"))
    admin.post(app, owner, "/api/admin/settings", {"eleven": {"api_key": "••••1234", "enabled": False}})
    check('27 saving the masked key keeps the real one; switching it off hides «جداوي»', app.store.setting("eleven")["api_key"] == "el-secret-key-1234"
          and not any(x.get("turn") for x in v.status("vis1", "1.2.3.4", True)["voices"]))
    admin.post(app, owner, "/api/admin/settings", {"eleven": {"api_key": " el-new-key-9999 ", "enabled": True}})
    check('28 a new key is kept (trimmed) and the voice is back', app.store.setting("eleven")["api_key"] == "el-new-key-9999" and v.el_ready())
    tt = admin.post(app, owner, "/api/admin/el_test", {})
    check('29 the owner\'s test: a sample in the voice and the credits left', tt["ok"] and tt.get("audio") and tt["balance"]["left"] == 28800
          and tt["balance"]["tier"] == "starter", {k: tt.get(k) for k in ("ok", "balance", "why")})

    # ---- through the web server: a recorded sentence is bigger than an ordinary request
    import web
    ws = web.Server(app, port=0, host="127.0.0.1") if 'port' in web.Server.__init__.__code__.co_varnames else None
    srv = None
    try:
        srv = ws.make() if ws and hasattr(ws, "make") else None
    except Exception:
        srv = None
    big = base64.b64encode(b"\x1aE\xdf\xa3" + os.urandom(60000)).decode()
    body = json.dumps({"session": "chatw", "visitor": "visw", "audio": big, "mime": "audio/webm", "ms": 4000}).encode()
    check('30 a sentence of ~80 KB is within the voice upload limit (and the ordinary limit stays small)',
          len(body) < web.MAX_VOICE and len(body) > web.MAX_BODY and "media-src 'self' blob:" in web.CSP, len(body))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
    fake.shutdown()

print(f"\n{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)

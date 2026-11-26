"""Voice salesman for the shop's site (GPT-Live) — prototype, shown to the shop's staff only until the owner approves.

How a call works
- The browser makes a WebRTC offer; this server forwards it to OpenAI (POST /v1/live/sessions) with the shop's key and
  hands back the answer. The key never leaves the server.
- GPT-Live listens and speaks. Everything about pieces, prices, stock and the shop's rules is delegated back to us
  ("client delegation"): the browser sends the customer's words to /api/voice/delegate, the same assistant that answers
  the text chat answers them (same tools, rules and checker, same customer file), the cards show on the screen, and the
  browser gives the checked answer to GPT-Live to say.
- To spend as little as possible the browser ends the call as soon as the customer is quiet and opens a new one when a
  speech detector on the phone hears real speech again (it costs nothing while closed). OpenAI bills at least 15 seconds
  for every opening, so the quiet delay before closing is a setting.
- Caps: per customer per day (higher once a customer is buying), a daily cap for voice, and the shop's monthly AI cap
  that the text assistant shares. When one is reached the microphone disappears and the text chat carries on.
"""
import datetime as dt
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request

LIVE_URL = "https://api.openai.com/v1/live/sessions"

DEFAULT = {
    "public": True,               # the microphone for everyone; the owner switches it off/on from the admin («المساعد الصوتي»)
    "model": "gpt-live-1",
    "voice": "echo",              # the default of the three voices below («سالم»)
    "per_customer_usd": 0.10,     # the most one customer can cost in a day
    "buyer_usd": 0.25,            # ... once he is buying (asked to buy, opened the purchase step)
    "daily_usd": 1.5,             # all voice calls in a day
    "price_per_min": 0.05,        # OpenAI's price for the voice layer, billed per second
    "min_billed_s": 15,           # OpenAI bills at least this much for every opening
    "close_after_ms": 2500,       # quiet (customer and assistant) this long -> the call closes until he speaks again
    "max_call_s": 300,            # one opening never runs longer than this (5 minutes); speaking again reopens it
    "max_live": 3,                # calls open at the same moment, for the whole shop
    "opens_per_10min": 10,        # openings per customer in ten minutes
    "ack_delay_ms": 800,          # pause before "one moment" while the shop's assistant looks (OpenAI allows 0-800); quick answers need none
    "standby": True,              # OpenAI's standby: quiet -> the call stays connected at the lower rate, wakes on speech
    "standby_after_s": 5,         # no words (either side) this long -> standby (OpenAI allows 5-60; 5 is the cheapest)
    "standby_per_min": 0.02,      # OpenAI's standby rate
    "standby_close_s": 20,        # in standby this long -> the call closes completely (free); the phone's detector reopens it
    "wake_threshold": 0.7,        # how sure OpenAI must be it is speech (not noise) to wake (0-1, its default 0.5)
    "test_mode": True,            # the owner's test: no per-person limit and no openings limit (only the day's cap), reasons shown
}

# the customer picks one of these from the call screen («تغيير الصوت»); each has its own name and manner
VOICES = [
    {"id": "echo", "name": "سالم", "g": "m", "sub": "صوت عميق", "style": "رجل هادي وواثق"},
    {"id": "ballad", "name": "فارس", "g": "m", "sub": "صوت دافئ", "style": "رجل بشوش ودافئ وواثق"},
    {"id": "coral", "name": "ريم", "g": "f", "sub": "صوت نسائي", "style": "بنت هادية وواثقة"},
]
VOICE_BY_ID = {x["id"]: x for x in VOICES}

GOLD_KNOWLEDGE = """معرفة عامة عن الذهب تقدر تقولها بنفسك (بدون أي رقم من أرقام المحل):
- عيار 21 يعني 21 جزء ذهب من 24، تقريباً 87.5٪ ذهب. عيار 24 أنقى وأطرى، و18 أقسى وفيه ذهب أقل. ذهبنا كله عيار 21، ومعه جنيهات ذهب.
- سعر الذهب يتغير كل يوم مع السوق العالمي وسعر الصرف، والمحل يحدد سعره اليومي. سعر البيع أعلى من سعر الشراء، وهذا طبيعي في كل محلات الذهب.
- لو بيشتري: يقارن على نفس الأساس (العيار والوزن والسعر النهائي)، ويطلب الوزن قدامه، وياخذ فاتورة فيها العيار والوزن ويحتفظ بها لأنها تنفعه لو باع بعدين. وما ينصح يشتري فوق ميزانيته؛ فيه قطع أخف بنفس الروح.
- لو هدفه الادخار، الجنيهات أنسب من المشغولات لأنها أسهل في البيع. ولو للبس والمناسبة، يختار اللي يعجبه ويناسب ميزانيته.
- لو بيبيع ذهبه: ينظفه ويجيب فاتورته لو عنده. السعر يعتمد على العيار والوزن وحالة الذهب، والتقييم النهائي في المحل.
- ما نسوي تبديل ذهب بذهب. يقدر يبيع ذهبه للمحل نقد، ويشتري اللي يعجبه.
- الحفظ: كل قطعة في كيس لحالها عشان ما تنخدش، بعيد عن العطور والمنظفات والكلور. تنظيف خفيف بماء دافي وصابون وفرشاة ناعمة، وتنشيف زين."""

PERSONA = """أنت «مستشار جمال المشرقي»، بيّاع ذهب بصوتك في موقع محل «جمال المشرقي للذهب والمجوهرات»، بجوار البوابة الرئيسية لمركز جرعان، إب.
الشخصية: رجل هادي وواثق، لهجة يمنية بيضاء محترمة، جمل قصيرة، سرعة متوسطة.
اللهجة: يمنية أو خليجية بيضاء فقط، في الكلمات والنطق. ممنوع الشامي والمصري نهائياً: لا تقول «شو، هلق، هيك، كتير، منيح، عم، بدك» ولا «إيه، إزيك، عايز، دلوقتي، كده، أوي، ده، دي، بتاع». قل بدالها «ايش أو وش، ايوه، الحين، كذا، كثير، زين، تبغى، هذا، هذي».
طريقة البيع: افهم الزبون قبل ما تعرض، سؤال واحد كل مرة وما تعيد سؤال جاوبه: تبغى الذهب للبس ولا للادخار؟ للبس: لبس يومي ولا لمناسبة وتبغاه لافت للحضور؟ ثم النوع، ثم الميزانية أو الوزن. بعدها اطلب القطع من الخلفية، والتزم بالميزانية والوزن بالضبط.
اختياراته: لو قال ضيفها لاختياراتي، أو كم مجموع اختياراتي، أو نكمل الشراء، أو وين أستلم: اطلب من الخلفية كل مرة، وقل اللي ترجعه. بعد ما يضيف قطعة اقترح يكمّل ميزانيته بقطعة تكمّلها. القاف لا تنطقها همزة، والجيم لا تنطقها مثل المصريين.
 تخاطب الزبون بصيغة المذكر العامة. بيّاع شاطر يبذل جهده بصدق، وكأنه بصف الزبون، مو موظف كول سنتر.

القاعدة الأهم: أي شي عن القطع والأسعار والأوزان والتوفر والطلبات والسياسات (الشراء، العربون، التبديل، الإرجاع، الإصلاح، التقسيط، الخصم، الدوام، الموقع) ما تقوله من عندك أبداً: اطلب من الخلفية في كل مرة، وانتظر نتيجتها، وقلها بصوتك بنفس المعنى والأرقام كما هي بالضبط. لا تخترع رقم ولا قطعة ولا وعد. القطع اللي تقترحها الخلفية تطلع للزبون على الشاشة.
وأنت تنتظر الخلفية: لو طلب شي جديد (قطع ثانية أو بحث) قل «لحظة أشوف لك» أو «أبشر، ثواني». ولو يسأل عن نفس القطعة اللي تتكلمون عنها قل «لحظة من فضلك» بس، أو لا تقول شي لو الجواب سريع. لا تكرر نفس كلمة الانتظار مرتين ورا بعض، ولا تقولها قبل كل رد.

ممنوع: ذكر فروع (المحل واحد)، كلمة «صالة» أو «مغتربين» أو «زيارة خاصة»، أي ذكر لقريبات الزبون، الاستعجال أو «آخر قطعة»، أي خصم أو تقسيط أو تبديل أو إرجاع من عندك، وذكر المصنعية أو تفصيل السعر (المصنعية داخلية؛ السعر نهائي وشامل كل شي على سعر ذهب اليوم).
لو سأل عن خصم أو يبغى يكلم شخص: فريق المبيعات على الواتساب، والزر على الشاشة.
لو ما فهمت كلامه: قل بصراحة «ما فهمت عليك زين، ممكن تعيدها؟». ولو تكرر مرتين، اقترح عليه يكتب طلبه في المحادثة.
لو قاطعك: اسكت فوراً واسمعه.
لما يبغى يشتري: أعد التفاصيل اللي جات من الخلفية (القطعة وسعرها) وأكدها معه، وقل إن زر الشراء أو الحجز على الشاشة. ما تأكد دفع ولا حجز بنفسك.

""" + GOLD_KNOWLEDGE

GREETING = "البداية: ترحيب قصير وعرّف باسمك، وسؤال واحد بس: «تبغى الذهب للبس ولا للادخار؟»"
RESUME = ("هذا استكمال لنفس المكالمة بعد سكوت قصير (المكالمة تتوقف لما يسكت الزبون وترجع لما يتكلم): لا ترحب من جديد "
          "ولا تعيد كلامك. لو الزبون يتكلم اسمعه وكمل معه من نفس المكان، ولو ساكت قل بس «تفضل، معك» بهدوء.")
BUSY = "المساعد الصوتي مشغول الحين، كمّل معي كتابة هنا أو كلم فريق المبيعات على الواتساب."


class Voice:
    def __init__(self, app):
        self.app, self.store, self.agent = app, app.store, app.agent
        self.lock = threading.Lock()
        self._warned = set()
        with app.lock:
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS voice_calls (
                id TEXT PRIMARY KEY, visitor TEXT, session TEXT, ip TEXT, day TEXT, started REAL, last_beat REAL,
                ended REAL, billed_s REAL DEFAULT 0, cost REAL DEFAULT 0, backend REAL DEFAULT 0, turns INTEGER DEFAULT 0,
                buyer INTEGER DEFAULT 0, lab INTEGER DEFAULT 0, oai_id TEXT, usage TEXT, end_reason TEXT, resumed INTEGER DEFAULT 0)""")
            cols = [r[1] for r in self.store.db.execute("PRAGMA table_info(voice_calls)").fetchall()]
            if "standby_s" not in cols:
                self.store.db.execute("ALTER TABLE voice_calls ADD COLUMN standby_s REAL DEFAULT 0")
            self.store.db.commit()
        threading.Thread(target=self._sweeper, daemon=True).start()

    # ---- settings and money
    def cfg(self):
        c = dict(DEFAULT)
        try:
            c.update({k: v for k, v in (self.store.setting("voice", {}) or {}).items() if k in DEFAULT})
        except Exception:
            pass
        return c

    def _today(self):
        return dt.date.today().isoformat()

    def _per_s(self, c):
        return float(c["price_per_min"]) / 60.0

    def _who(self, visitor, ip):
        return (visitor or "")[:40] or ("ip:" + (ip or "?"))

    def _spent_by(self, who):
        r = self.store.one("SELECT COALESCE(SUM(cost+backend),0) c, MAX(buyer) b FROM voice_calls WHERE day=? AND visitor=?",
                           (self._today(), who))
        return float(r["c"] or 0), bool(r["b"])

    def _spent_voice_today(self):
        return float(self.store.one("SELECT COALESCE(SUM(cost+backend),0) c FROM voice_calls WHERE day=?", (self._today(),))["c"] or 0)

    def _cost(self, c, billed, standby):
        """Active seconds at the full rate, standby seconds at the lower rate."""
        sb = max(0.0, min(float(standby or 0), billed))
        return (billed - sb) * self._per_s(c) + sb * float(c["standby_per_min"]) / 60.0

    @staticmethod
    def _sb(row):
        try:
            return float(row["standby_s"] or 0)
        except Exception:
            return 0.0

    def _live_cost(self, row, now, c):
        """What an open call has cost so far: at least the minimum OpenAI bills for an opening."""
        return self._cost(c, max(float(c["min_billed_s"]), now - float(row["started"])), self._sb(row))

    def _note_standby(self, row, standby_ms, now):
        """The phone reports how long OpenAI kept the call in standby (its paused/resumed events); never more than
        the call's own time, and never less than before."""
        try:
            sb = max(0.0, float(standby_ms) / 1000.0)
        except Exception:
            return
        sb = min(sb, max(0.0, now - float(row["started"])))
        if sb > self._sb(row):
            with self.app.lock:
                self.store.db.execute("UPDATE voice_calls SET standby_s=? WHERE id=?", (round(sb, 1), row["id"]))
                self.store.db.commit()

    def _budget_left(self, who, c, extra=0.0, lab=False):
        spent, buyer = self._spent_by(who)
        cap = float(c["daily_usd"] if (lab or c.get("test_mode")) else c["buyer_usd"] if buyer else c["per_customer_usd"])   # testing: only the day's cap
        day_left = float(c["daily_usd"]) - self._spent_voice_today()
        return max(0.0, min(cap - spent, day_left) - extra), buyer

    # ---- who may use it now
    def status(self, visitor, ip, lab):
        c = self.cfg()
        out = {"on": False, "close_after_ms": c["close_after_ms"], "lab": bool(lab), "test": bool(c.get("test_mode"))}
        ai = self.agent.cfg()
        if not (lab or c["public"]):
            out["why"] = "hidden"
            return out
        if not (ai.get("enabled") and ai.get("api_key")):
            out["why"] = "off"
            return out
        day, month = self.agent._spent()
        if month >= float(ai["monthly_cap_usd"]):
            out["why"] = "monthly"
            return out
        if self._spent_voice_today() >= float(c["daily_usd"]):
            out["why"] = "daily"
            return out
        left, buyer = self._budget_left(self._who(visitor, ip), c, lab=lab)
        if left * 1.0 < float(c["min_billed_s"]) * self._per_s(c):
            out["why"] = "customer"
            return out
        out.update({"on": True, "budget_s": int(left / self._per_s(c)), "buyer": buyer})
        out.update({"voices": [{k: x[k] for k in ("id", "name", "g", "sub")} for x in VOICES], "voice": c.get("voice")})
        return out

    # ---- open a call
    def _history(self, session, n=10):
        rows = self.store.q("SELECT role, content FROM chat_logs WHERE session=? ORDER BY id DESC LIMIT ?", (session, n))
        lines = []
        for r in reversed(rows):
            txt = re.sub(r"\[\[[A-Za-z0-9]+\]\]", "", r["content"] or "").strip()
            if txt:
                lines.append(("الزبون: " if r["role"] == "user" else "أنت: ") + txt[:300])
        return "\n".join(lines)

    def _instructions(self, session, resume, voice=None):
        hist = self._history(session)
        persona = PERSONA
        v = VOICE_BY_ID.get(voice or "")
        if v:
            if v["g"] == "f":
                persona = persona.replace("أنت «مستشار جمال المشرقي»، بيّاع ذهب", "أنتِ «" + v["name"] + "»، مستشارة جمال المشرقي، بيّاعة ذهب", 1)
                persona = persona.replace("الشخصية: رجل هادي وواثق", "الشخصية: " + v["style"] + "، تتكلم عن نفسها بصيغة المؤنث (أنا جاهزة، أنا معك)", 1)
            else:
                persona = persona.replace("أنت «مستشار جمال المشرقي»، بيّاع ذهب", "أنت «" + v["name"] + "»، مستشار جمال المشرقي، بيّاع ذهب", 1)
                persona = persona.replace("الشخصية: رجل هادي وواثق", "الشخصية: " + v["style"], 1)
            persona += "\nاسمك «" + v["name"] + "»: عرّف بنفسك باسمك مرة وحدة في أول رد، ولو سألك الزبون عن اسمك قله."
        parts = [persona, RESUME if resume else GREETING]
        if hist:
            parts.append("اللي صار في المحادثة إلى الآن (كتابة أو صوت):\n" + hist)
        return "\n\n".join(parts)

    def _post(self, key, body, timeout=20):
        req = urllib.request.Request(LIVE_URL, json.dumps(body).encode(), {"Authorization": "Bearer " + key,
                                                                           "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except Exception:
                return e.code, {}
        except Exception as e:
            return 0, {"error": {"message": str(e)[:200]}}

    def open(self, visitor, session, sdp, ip, lab, resume=False, voice=None):
        c = self.cfg()
        session = re.sub(r"[^A-Za-z0-9_-]", "", session or "")[:40]
        who = self._who(visitor, ip)
        if not sdp or len(sdp) > 30000 or not session:
            return {"ok": False, "why": "bad"}
        st = self.status(visitor, ip, lab)
        if not st["on"]:
            why = {"hidden": "الصوت موقّف من لوحة الإدارة", "off": "المساعد مطفي أو ما فيه مفتاح", "monthly": "الحد الشهري خلص",
                   "daily": "حد الصوت اليومي خلص", "customer": "حد هذا الزبون اليومي خلص"}.get(st.get("why"), st.get("why") or "")
            return {"ok": False, "why": st.get("why"), "say": BUSY, "detail": why if (lab or c.get("test_mode")) else ""}
        now = time.time()
        with self.lock:
            live = self.store.one("SELECT COUNT(*) n FROM voice_calls WHERE ended IS NULL AND last_beat>?", (now - 30,))["n"]
            recent = self.store.one("SELECT COUNT(*) n FROM voice_calls WHERE visitor=? AND started>?", (who, now - 600))["n"]
        if live >= int(c["max_live"]):
            return {"ok": False, "why": "busy", "say": BUSY}
        if recent >= int(c["opens_per_10min"]) and not c.get("test_mode"):
            return {"ok": False, "why": "rate", "say": BUSY}
        key = self.agent.cfg().get("api_key")
        try:
            ack = max(0, min(800, int(c.get("ack_delay_ms", 800))))        # OpenAI accepts 0 to 800
        except Exception:
            ack = 600
        sess = {"model": c["model"], "instructions": self._instructions(session, resume),
                "delegation": {"type": "client", "acknowledgement_delay_ms": ack}}
        vname = voice if voice in VOICE_BY_ID else c.get("voice")
        sess["instructions"] = self._instructions(session, resume, vname)
        if vname:
            sess["audio"] = {"output": {"voice": vname}}
        if c.get("standby"):
            sess["idle_timeout_s"] = max(5, min(60, int(c.get("standby_after_s", 5))))
            sess["wake_policy"] = {"type": "speech", "vad_threshold": max(0.0, min(1.0, float(c.get("wake_threshold", 0.6))))}
        code, d = self._post(key, {"session": sess, "transport": {"type": "webrtc", "sdp": sdp}})
        dropped = []
        for _ in range(3):                         # an optional setting OpenAI refuses: drop it and try again, once each
            if code != 400:
                break
            err = json.dumps(d).lower()
            if "audio" in sess and "voice" in err:
                sess.pop("audio"); dropped.append("voice")          # a voice name it does not offer: its default voice (marin)
                sess["instructions"] = self._instructions(session, resume, "marin")
            elif "acknowledgement_delay_ms" in err and "acknowledgement_delay_ms" in sess["delegation"]:
                sess["delegation"].pop("acknowledgement_delay_ms"); dropped.append("ack")
            elif ("idle_timeout" in err or "wake_policy" in err) and "idle_timeout_s" in sess:
                sess.pop("idle_timeout_s"); sess.pop("wake_policy", None); dropped.append("standby")   # back to closing when quiet
            else:
                break
            code, d = self._post(key, {"session": sess, "transport": {"type": "webrtc", "sdp": sdp}})
        if dropped and code in (200, 201):
            self._warn(0, "اشتغلت المكالمة بعد ما شلت إعداد رفضه OpenAI: " + "، ".join(dropped), ok=True)
        if code not in (200, 201) or not (d.get("transport") or {}).get("sdp"):
            msg = ((d.get("error") or {}).get("message") or "")[:300]
            self._warn(code, msg)
            return {"ok": False, "why": "openai", "code": code, "detail": msg if (lab or c.get("test_mode")) else "", "say": BUSY}
        cid = secrets.token_hex(8)
        with self.lock, self.app.lock:
            self.store.db.execute("INSERT INTO voice_calls (id,visitor,session,ip,day,started,last_beat,lab,oai_id,resumed) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (cid, who, session, (ip or "")[:60], self._today(), now, now, 1 if lab else 0,
                                   (d.get("session") or {}).get("id"), 1 if resume else 0))
            self.store.db.commit()
        left = max(0.0, st["budget_s"] * self._per_s(c))
        sb = int(sess.get("idle_timeout_s") or 0)
        return {"ok": True, "call": cid, "sdp": d["transport"]["sdp"], "budget_s": int(left / self._per_s(c)),
                "standby_s": sb, "close_after_ms": int(c["standby_close_s"]) * 1000 if sb else c["close_after_ms"],
                "max_call_s": c["max_call_s"], "voice": (sess.get("audio") or {}).get("output", {}).get("voice", "")}

    def _warn(self, code, msg, ok=False):
        """OpenAI refused the call (no access to the model, no balance...): tell the owner in plain words,
        each kind of problem once a day."""
        today = self._today()
        if getattr(self, "_warn_day", None) != today:
            self._warn_day, self._warned = today, set()
        k = (code, (msg or "")[:60])
        if k in self._warned:
            return
        self._warned.add(k)
        why = ("تنبيه" if ok else "الحساب ما عنده صلاحية للنموذج الصوتي أو رصيده ما يكفي" if code in (401, 402, 403, 404, 429)
               else "OpenAI رفض فتح المكالمة")
        try:
            note = getattr(self.agent, "notify", None)
            if note:
                note(f"🎙️ المساعد الصوتي: {why}" + (f" (رمز {code})" if code else "") + f". {msg[:160]}")
        except Exception:
            pass

    # ---- during a call
    def _row(self, cid):
        return self.store.one("SELECT * FROM voice_calls WHERE id=?", ((cid or "")[:20],))

    def beat(self, cid, standby_ms=None):
        c = self.cfg()
        row = self._row(cid)
        if not row or row["ended"]:
            return {"ok": False, "left_s": 0}
        now = time.time()
        with self.lock:
            if standby_ms is not None:
                self._note_standby(row, standby_ms, now)
            with self.app.lock:
                self.store.db.execute("UPDATE voice_calls SET last_beat=? WHERE id=?", (now, row["id"]))
                self.store.db.commit()
        row = self._row(cid)
        call = self._live_cost(row, now, c) + self._backend_cost(row["session"], float(row["started"]), now)
        return {"ok": True, "left_s": self._left_s(row, now, c), "call_usd": round(call, 4),
                "today_usd": round(self._spent_voice_today() + call, 4)}

    def _left_s(self, row, now, c):
        left, _ = self._budget_left(row["visitor"], c, extra=self._live_cost(row, now, c), lab=bool(row["lab"]))
        left_s = int(left / self._per_s(c))
        return max(0, min(left_s, int(c["max_call_s"]) - int(now - float(row["started"]))))

    def delegate(self, cid, text, picks=None):
        c = self.cfg()
        row = self._row(cid)
        if not row or row["ended"]:
            return {"say": BUSY, "stop": True}
        text = (text or "").strip()[:600]
        if not text:
            return {"say": "ما فهمت عليك زين، ممكن تعيدها؟", "pieces": [], "misheard": True,
                    "left_s": self._left_s(row, time.time(), c)}
        who = row["visitor"] if not row["visitor"].startswith("ip:") else None
        res = (self.agent.chat(row["session"], text, who, picks) if picks is not None else self.agent.chat(row["session"], text, who)) or {}
        buyer = bool(res.get("offer")) or res.get("stage") in ("ready", "closing")
        with self.lock, self.app.lock:
            self.store.db.execute("UPDATE voice_calls SET turns=turns+1, buyer=MAX(buyer,?) WHERE id=?",
                                  (1 if buyer else 0, row["id"]))
            self.store.db.commit()
        say = re.sub(r"\[\[[A-Za-z0-9]+\]\]", "", res.get("text") or "").strip()
        say = say.replace("الزر تحت", "الزر على الشاشة").replace("تحت المحادثة", "على الشاشة")
        say = re.sub(r"\n{2,}", "\n", say) or "خلني أتأكد لك وأرجع لك."
        out = {"say": say, "text": res.get("text") or "", "pieces": res.get("pieces") or [], "suggest": res.get("suggest") or [],
               "left_s": self._left_s(self._row(cid), time.time(), c)}
        for k in ("offer", "handoff", "add_picks"):
            if k in res:
                out[k] = res[k]
        return out

    # ---- end of a call
    def close(self, cid, usage=None, reason="end", standby_ms=None):
        c = self.cfg()
        with self.lock:
            row = self._row(cid)
            if not row or row["ended"]:
                return {"ok": True}
            now = time.time()
            end = now if reason != "stale" else min(now, float(row["last_beat"]) + 10)
            if standby_ms is not None:
                self._note_standby(row, standby_ms, end)
                row = self._row(cid)
            billed = max(float(c["min_billed_s"]), end - float(row["started"]))
            cost = round(self._cost(c, billed, self._sb(row)), 5)
            backend = self._backend_cost(row["session"], float(row["started"]), end)
            with self.app.lock:
                self.store.db.execute("UPDATE voice_calls SET ended=?, billed_s=?, cost=?, backend=?, usage=?, end_reason=? WHERE id=?",
                                      (end, round(billed, 1), cost, backend, json.dumps(usage, ensure_ascii=False)[:2000] if usage else None,
                                       (reason or "end")[:20], row["id"]))
                self.store.db.commit()
        an = getattr(self.agent, "analytics", None)
        if an:   # the voice layer counts against the same daily / monthly caps as the text assistant
            an.log_ai(row["session"], c["model"], "voice", "voice", "voice:" + (reason or "end")[:12], 0, 0, 0, cost,
                      int(billed * 1000), "")
        return {"ok": True, "billed_s": round(billed, 1), "standby_s": round(min(self._sb(row), billed), 1), "cost": cost}

    def _backend_cost(self, session, t0, t1):
        an = getattr(self.agent, "analytics", None)
        if not an:
            return 0.0
        a = dt.datetime.fromtimestamp(t0).isoformat(sep=" ")
        b = dt.datetime.fromtimestamp(t1 + 5).isoformat(sep=" ")
        try:
            r = an.db.execute("SELECT COALESCE(SUM(cost),0) FROM ai_usage WHERE session=? AND kind!='voice' AND ts BETWEEN ? AND ?",
                              (session, a, b)).fetchone()
            return round(float(r[0]), 5)
        except Exception:
            return 0.0

    def _sweeper(self):
        """A phone that vanished (closed tab, lost network): its call is closed after 25 quiet seconds."""
        while True:
            time.sleep(15)
            try:
                rows = self.store.q("SELECT id FROM voice_calls WHERE ended IS NULL AND last_beat<?", (time.time() - 25,))
                for r in rows:
                    self.close(r["id"], None, "stale")
            except Exception as e:
                print("voice sweeper:", e, flush=True)

    # ---- the owner's report
    def report(self, a, b):
        rows = self.store.q("SELECT * FROM voice_calls WHERE day BETWEEN ? AND ? ORDER BY started DESC", (a, b))
        tot = {"calls": len(rows), "seconds": round(sum(r["billed_s"] or 0 for r in rows)),
               "cost": round(sum((r["cost"] or 0) + (r["backend"] or 0) for r in rows), 4),
               "customers": len({r["visitor"] for r in rows}), "buyers": len({r["visitor"] for r in rows if r["buyer"]})}
        recent = [{"when": dt.datetime.fromtimestamp(r["started"]).strftime("%m-%d %H:%M"), "who": (r["visitor"] or "")[:8],
                   "seconds": r["billed_s"], "voice": r["cost"], "backend": r["backend"], "turns": r["turns"],
                   "buyer": bool(r["buyer"]), "lab": bool(r["lab"]), "reason": r["end_reason"] or "مفتوحة"} for r in rows[:40]]
        c = self.cfg()
        return {"totals": tot, "recent": recent, "today": round(self._spent_voice_today(), 4),
                "caps": {"customer": c["per_customer_usd"], "buyer": c["buyer_usd"], "day": c["daily_usd"]},
                "price_per_min": c["price_per_min"], "public": c["public"], "test_mode": bool(c.get("test_mode"))}

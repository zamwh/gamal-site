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

«رد ورد» voices (all OpenAI, the cheaper way)
- No call stays open: the phone records one sentence (its own speech detector decides when he stopped), sends it here,
  OpenAI turns it into text, the same shop assistant answers, OpenAI's speech model reads the answer in the chosen
  voice, and the phone plays it. Nothing is paid while he is quiet. The same sentence in the same voice is made once
  and kept (a greeting costs nothing the second time).
"""
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from speak_ar import speakable

LIVE_URL = "https://api.openai.com/v1/live/sessions"
STT_URL = "https://api.openai.com/v1/audio/transcriptions"
TTS_URL = "https://api.openai.com/v1/audio/speech"

DEFAULT = {
    "public": True,               # the microphone for everyone; the owner switches it off/on from the admin («المساعد الصوتي»)
    "model": "gpt-live-1",
    "voice": "t:echo",            # the default voice: «سالم» answering turn by turn (the cheapest)
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
    # «رد ورد» voices: his words -> text, the shop's assistant answers, OpenAI's speech model says it
    "stt_model": "gpt-4o-mini-transcribe",
    "stt_per_min": 0.003,         # OpenAI's price for turning his words into text
    "tts_model": "gpt-4o-mini-tts",
    "tts_per_min": 0.015,         # OpenAI's price for the spoken answer (about 1.5 cents a minute of speech)
    "tts_in_per_m": 0.60,         # ... plus its text in, per million tokens
    "tts_max_chars": 320,         # a long written answer: the voice reads its first sentences, the rest stays on the screen
    "turn_max_s": 25,             # the longest the phone records one sentence
}

# «رد ورد»: the same three voices, answering one sentence at a time through OpenAI's speech model
TURN_VOICES = [{"id": "t:echo", "oai": "echo", "name": "سالم", "g": "m", "sub": "رد ورد · الأوفر", "turn": True},
               {"id": "t:ballad", "oai": "ballad", "name": "فارس", "g": "m", "sub": "رد ورد · الأوفر", "turn": True},
               {"id": "t:coral", "oai": "coral", "name": "ريم", "g": "f", "sub": "رد ورد · الأوفر", "turn": True}]
TURN_BY_ID = {x["id"]: x for x in TURN_VOICES}
TTS_STYLE = {"m": "تكلم بالعربي بلهجة خليجية بيضاء، بصوت رجل واثق ومبتسم وودود، مثل بيّاع ذهب يسولف مع زبونه، مو مثل واحد يقرأ. "
                  "سرعة طبيعية مثل الكلام اليومي، نبرة حية متنوعة، ونطق واضح لكل حرف وللأرقام والأسعار. "
                  "انطق: المَشْرِقي، جَرْعان، إِبّ، مُجَوْهَرات، عِيار واحِد وعِشْرين.",
             "f": "تكلمي بالعربي بلهجة خليجية بيضاء، بصوت بنت واثقة ومبتسمة وودودة، مثل مستشارة ذهب تسولف مع زبونها، مو مثل وحدة تقرأ. "
                  "سرعة طبيعية مثل الكلام اليومي، نبرة حية متنوعة، ونطق واضح لكل حرف وللأرقام والأسعار. "
                  "انطقي: المَشْرِقي، جَرْعان، إِبّ، مُجَوْهَرات، عِيار واحِد وعِشْرين."}
# the opening is light: a welcome with the shop's full name and «how can I help», no sales question yet
HELLO_T = ["حياك الله في جمال المشرقي للذهب والمجوهرات. كيف أقدر أخدمك اليوم؟",
           "هلا والله فيك في جمال المشرقي للذهب والمجوهرات. كيف أقدر أساعدك اليوم؟",
           "أهلاً وسهلاً فيك في جمال المشرقي للذهب والمجوهرات، أنا مستشارك. تفضل، كيف أقدر أخدمك؟",
           "يا هلا ومرحبا، معك مستشار جمال المشرقي للذهب والمجوهرات. كيف أقدر أساعدك اليوم؟",
           "مرحبا بك في جمال المشرقي للذهب والمجوهرات. تفضل، وش أقدر أسوي لك اليوم؟"]
HELLO_BACK = ["هلا فيك، أنا معك بالصوت الحين. تفضل، كلمني.",
              "حياك الله، صرت أسمعك. تفضل قل لي وش تبغى.",
              "أهلاً، أنا معك. تكلم براحتك."]
MISHEARD = "ما سمعتك زين، ممكن تعيدها؟"
STT_PROMPT = ("زبون يكلم محل ذهب في إب باللهجة اليمنية أو الخليجية. كلمات تتكرر: ذهب، عيار 21، جنيه، سبيكة، خاتم، عقد، "
              "سلسلة، أسوارة، حلق، طقم، تعليقة، جرام، ريال، مليون، ألف، ميزانيتي، للبس، للادخار، يومي، مناسبة، اختياراتي، نكمل الشراء.")
JUNK = re.compile(r"نانسي|قنقر|اشتركوا|اشترك في|لمشاهدتكم|للمشاهدة|ترجمة|subtitle|amara|\bmusic\b|موسيقى", re.I)

# the customer picks one of these from the call screen («تغيير الصوت»); each has its own name and manner
VOICES = [
    {"id": "echo", "name": "سالم", "g": "m", "sub": "صوت عميق", "style": "رجل واثق ومبتسم، كلامه خفيف وحي"},
    {"id": "ballad", "name": "فارس", "g": "m", "sub": "صوت دافئ", "style": "رجل بشوش ودافئ، كلامه خفيف وحي"},
    {"id": "coral", "name": "ريم", "g": "f", "sub": "صوت نسائي", "style": "بنت واثقة ومبتسمة، كلامها خفيف وحي"},
]
VOICE_BY_ID = {x["id"]: x for x in VOICES}

GOLD_KNOWLEDGE = """معرفة عامة عن الذهب تقدر تقولها بنفسك (بدون أي رقم من أرقام المحل):
- عيار 21 يعني 21 جزء ذهب من 24، تقريباً 87.5٪ ذهب. عيار 24 أنقى وأطرى، و18 أقسى وفيه ذهب أقل. ذهبنا كله عيار 21، ومعه جنيهات ذهب.
- سعر الذهب يتغير كل يوم مع السوق العالمي وسعر الصرف، والمحل يحدد سعره اليومي. سعر البيع أعلى من سعر الشراء، وهذا طبيعي في كل محلات الذهب.
- لو بيشتري: يقارن على نفس الأساس (العيار والوزن والسعر النهائي)، ويطلب الوزن قدامه، وياخذ فاتورة فيها العيار والوزن ويحتفظ بها لأنها تنفعه لو باع بعدين. وما ينصح يشتري فوق ميزانيته؛ فيه قطع أخف بنفس الروح.
- لو هدفه الادخار، الجنيهات أنسب من المشغولات لأنها أسهل في البيع. ولو للزينة والمناسبة، يختار اللي يعجبه ويناسب ميزانيته.
- لو بيبيع ذهبه: ينظفه ويجيب فاتورته لو عنده. السعر يعتمد على العيار والوزن وحالة الذهب، والتقييم النهائي في المحل.
- ما نسوي تبديل ذهب بذهب. يقدر يبيع ذهبه للمحل نقد، ويشتري اللي يعجبه.
- الحفظ: كل قطعة في كيس لحالها عشان ما تنخدش، بعيد عن العطور والمنظفات والكلور. تنظيف خفيف بماء دافي وصابون وفرشاة ناعمة، وتنشيف زين."""

PERSONA = """أنت «مستشار جمال المشرقي»، بيّاع ذهب بصوتك في موقع محل «جمال المشرقي للذهب والمجوهرات»، بجوار البوابة الرئيسية لمركز جرعان، إب.
الشخصية: رجل هادي وواثق، مبتسم وكلامه خفيف، جمل قصيرة.
اللهجة: خليجية بيضاء (مثل أهل جدة والرياض) في الكلمات والنطق، لأنها أوضح وأخف على السمع.
طريقة الكلام: تكلم مثل بيّاع حقيقي يسولف مع زبونه، مو مثل واحد يقرأ ورقة ولا مثل إعلان.
- سرعة طبيعية مثل الكلام اليومي، لا بطيء ثقيل ولا مستعجل. نوّع في نبرتك، وخذ نفس طبيعي بين الجمل.
- غيّر نبرتك حسب الموقف: لو الزبون مزح أو ضحك اضحك ضحكة خفيفة طبيعية ورد بروح حلوة. لو عجبته قطعة افرح معه. لو متردد طمّنه بهدوء. لو مستعجل اختصر.
- الكلام اليومي: «هلا والله، أبشر، تمام، على راسي، ولا يهمك، يعطيك العافية» في مكانها، بدون مبالغة ولا تكرار.
- الأرقام والأسعار قلها بالكلمات العربية واضحة، مثل «مية وتسعين ألف ريال»، و«ثلاثة جرام ونص».
النطق الصحيح (انطق هذي الكلمات كذا بالضبط):
- المَشْرِقي (الميم مفتوحة، والشين ساكنة، والراء مكسورة)، جَرْعان (الجيم مفتوحة، والراء ساكنة)، إِبّ (الهمزة مكسورة، والباء مشددة)
- مُجَوْهَرات، تَشْكِيلات، حَصْرِيّة، عِيار واحِد وعِشْرين، جِنَيْه، سَبِيكة، خاتَم، عِقْد، سِلْسِلة، أَسْوِرة، طَقْم، حَلَق، جْرام
- كل حرف واضح ومخرجه صحيح، والكلمة كاملة بدون ما تبلع آخرها.
- لا تقول «للبس» أبداً (تطلع كأنها «للبَسّ»)، ولا «تلبسه» (الزبون غالباً رجال يشتري لغيره)، قل «للزينة». واسم المحل كامل: «جمال المشرقي للذهب والمجوهرات».

مهارات البيّاع الشاطر:
- ردك قصير: جملة أو جملتين، وبعدها سؤال واحد أو خطوة وحدة. لا تخطب.
- لو قال اسمه، ناديه باسمه بين فترة وفترة.
- لما تعرض قطعة: صفها من بياناتها اللي جات من الخلفية بكلام يحمّس (شكلها، لمعتها، كيف تطلع وهي ملبوسة، تناسب أي مناسبة)، بدون ما تخترع شي مو فيها.
- اعرض قطعتين أو ثلاث بالكثير، وقل ليش كل وحدة تناسبه من كلامه هو، وبعدها اسأل «أي وحدة شدتك أكثر؟».
- لو قال غالية: لا تجادل. السعر وزن الذهب على سعر اليوم، واقترح قطعة أخف بنفس الشكل من الخلفية.
- لو متردد: طمّنه (فاتورة فيها العيار والوزن، والسعر بسعر اليوم)، وخلّ القرار له بدون ضغط.
- لو عجبته قطعة: اقترح بلطف قطعة تكمّلها (حلق مع العقد، خاتم مع الأسوارة) مرة وحدة بس.
- لو بان إنه جاهز يشتري: أكّد القطعة وسعرها من الخلفية، وقل له زر الشراء أو الحجز على الشاشة.
- في الختام: اشكره بحرارة وقل «نتشرف فيك في جمال المشرقي للذهب والمجوهرات». ممنوع الشامي والمصري نهائياً: لا تقول «شو، هلق، هيك، كتير، منيح، عم، بدك» ولا «إيه، إزيك، عايز، دلوقتي، كده، أوي، ده، دي، بتاع». قل بدالها «ايش أو وش، ايوه، الحين، كذا، كثير، زين، تبغى، هذا، هذي».
الأسلوب: خفيف ولطيف، مو على طول بيع. أول رد للزبون: رد على كلامه هو بطبيعية (سلام، سؤال، سوالف)، وبعدها ادخل في الذهب بهدوء لما يناسب الكلام.
طريقة البيع: افهم الزبون قبل ما تعرض، سؤال واحد كل مرة وما تعيد سؤال جاوبه: تبغى الذهب للزينة ولا للادخار؟ لو للزينة: للاستخدام اليومي ولا لمناسبة وتبغاه لافت للحضور؟ ثم النوع، ثم الميزانية أو الوزن. بعدها اطلب القطع من الخلفية، والتزم بالميزانية والوزن بالضبط.
اختياراته: لو قال ضيفها لاختياراتي، أو كم مجموع اختياراتي، أو نكمل الشراء، أو وين أستلم: اطلب من الخلفية كل مرة، وقل اللي ترجعه. بعد ما يضيف قطعة اقترح يكمّل ميزانيته بقطعة تكمّلها. القاف لا تنطقها همزة (قلها قاف أو مثل الخليج «ڨ»)، والجيم لا تنطقها مثل المصريين.
 تخاطب الزبون بصيغة المذكر العامة. بيّاع شاطر يبذل جهده بصدق، وكأنه بصف الزبون، مو موظف كول سنتر.

القاعدة الأهم: أي شي عن القطع والأسعار والأوزان والتوفر والطلبات والسياسات (الشراء، العربون، التبديل، الإرجاع، الإصلاح، التقسيط، الخصم، الدوام، الموقع) ما تقوله من عندك أبداً: اطلب من الخلفية في كل مرة، وانتظر نتيجتها، وقلها بصوتك بنفس المعنى والأرقام كما هي بالضبط. لا تخترع رقم ولا قطعة ولا وعد. القطع اللي تقترحها الخلفية تطلع للزبون على الشاشة.
وأنت تنتظر الخلفية: لو طلب شي جديد (قطع ثانية أو بحث) قل «لحظة أشوف لك» أو «أبشر، ثواني». ولو يسأل عن نفس القطعة اللي تتكلمون عنها قل «لحظة من فضلك» بس، أو لا تقول شي لو الجواب سريع. لا تكرر نفس كلمة الانتظار مرتين ورا بعض، ولا تقولها قبل كل رد.

ممنوع: ذكر فروع (المحل واحد)، كلمة «صالة» أو «مغتربين» أو «زيارة خاصة»، أي ذكر لقريبات الزبون، الاستعجال أو «آخر قطعة»، أي خصم أو تقسيط أو تبديل أو إرجاع من عندك، وذكر المصنعية أو تفصيل السعر (المصنعية داخلية؛ السعر نهائي وشامل كل شي على سعر ذهب اليوم).
لو سأل عن خصم أو يبغى يكلم شخص: فريق المبيعات على الواتساب، والزر على الشاشة.
لو ما فهمت كلامه: قل بصراحة «ما فهمت عليك زين، ممكن تعيدها؟». ولو تكرر مرتين، اقترح عليه يكتب طلبه في المحادثة.
لو قاطعك: اسكت فوراً واسمعه.
لما يبغى يشتري: أعد التفاصيل اللي جات من الخلفية (القطعة وسعرها) وأكدها معه، وقل إن زر الشراء أو الحجز على الشاشة. ما تأكد دفع ولا حجز بنفسك.

""" + GOLD_KNOWLEDGE

GREETING = ("البداية: ترحيب قصير لطيف فيه اسم المحل كامل «جمال المشرقي للذهب والمجوهرات» (مو «جمال المشرقي» بس، ولا «نورت»)، "
            "وعرّف باسمك، وبعدها «كيف أقدر أخدمك اليوم؟» بس. لا تسأل عن الذهب ولا الميزانية في الترحيب.")
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
            self.store.db.execute("""CREATE TABLE IF NOT EXISTS voice_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT, visitor TEXT, session TEXT, ip TEXT, day TEXT, ts REAL, kind TEXT,
                stt_s REAL DEFAULT 0, stt_cost REAL DEFAULT 0, chars INTEGER DEFAULT 0, credits REAL DEFAULT 0,
                tts_cost REAL DEFAULT 0, backend REAL DEFAULT 0, cached INTEGER DEFAULT 0, lab INTEGER DEFAULT 0,
                buyer INTEGER DEFAULT 0, ms INTEGER DEFAULT 0, err TEXT)""")
            self.store.db.commit()
        self._tts_n = 0
        try:                                       # ElevenLabs («جداوي») was removed (27 Nov): its saved key goes too
            if self.store.setting("eleven", None):
                with app.lock:
                    self.store.set_setting("eleven", {})
        except Exception:
            pass
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
        t = self.store.one("SELECT COALESCE(SUM(stt_cost+tts_cost+backend),0) c, MAX(buyer) b FROM voice_turns WHERE day=? AND visitor=?",
                           (self._today(), who))
        return float(r["c"] or 0) + float(t["c"] or 0), bool(r["b"] or t["b"])

    def _spent_voice_today(self):
        a = self.store.one("SELECT COALESCE(SUM(cost+backend),0) c FROM voice_calls WHERE day=?", (self._today(),))["c"]
        b = self.store.one("SELECT COALESCE(SUM(stt_cost+tts_cost+backend),0) c FROM voice_turns WHERE day=?", (self._today(),))["c"]
        return float(a or 0) + float(b or 0)

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
        voices = [{k: x[k] for k in ("id", "name", "g", "sub", "turn") if k in x} for x in TURN_VOICES + VOICES]
        dv = c.get("voice") if (c.get("voice") in VOICE_BY_ID or c.get("voice") in TURN_BY_ID) else "t:echo"
        out.update({"voices": voices, "voice": dv})
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
        vname = voice if voice in VOICE_BY_ID else (c.get("voice") if c.get("voice") in VOICE_BY_ID else "echo")
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

    def _warn(self, code, msg, ok=False, why=None):
        """OpenAI refused the call (no access to the model, no balance...): tell the owner in plain words,
        each kind of problem once a day."""
        today = self._today()
        if getattr(self, "_warn_day", None) != today:
            self._warn_day, self._warned = today, set()
        k = (code, (msg or "")[:60])
        if k in self._warned:
            return
        self._warned.add(k)
        why = why or ("تنبيه" if ok else "الحساب ما عنده صلاحية للنموذج الصوتي أو رصيده ما يكفي" if code in (401, 402, 403, 404, 429)
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

    # ---- «رد ورد» voices (OpenAI): one sentence at a time, nothing paid while he is quiet
    def _tts_dir(self):
        d = os.path.join(self.store.base_dir, "tts", self.store.mode)
        os.makedirs(d, exist_ok=True)
        return d

    def _tts_cost(self, c, text, model):
        """OpenAI does not report it per answer: about 14 letters a second of Arabic speech, the text in by tokens."""
        if model == "tts-1":
            return len(text) * 15.0 / 1e6
        return (len(text) / 14.0 / 60.0) * float(c["tts_per_min"]) + (len(text) / 2.5) * float(c["tts_in_per_m"]) / 1e6

    def _tts(self, text, tv, c):
        """(mp3, cost, from the kept copy?, problem). The same words in the same voice are made only once."""
        text = (text or "").strip()[:900]
        if not text:
            return None, 0.0, False, None
        style = TTS_STYLE.get(tv.get("g"), TTS_STYLE["m"])
        first = c.get("tts_model") or "gpt-4o-mini-tts"
        sig = "|".join([tv["oai"], first, style, text])
        fp = os.path.join(self._tts_dir(), hashlib.sha1(sig.encode()).hexdigest()[:28] + ".mp3")
        try:
            with open(fp, "rb") as f:
                data = f.read()
            if data:
                try:
                    os.utime(fp, None)
                except OSError:
                    pass
                return data, 0.0, True, None
        except OSError:
            pass
        key = self.agent.cfg().get("api_key")
        last = ""
        for m in [first] + [x for x in ("gpt-4o-mini-tts", "tts-1") if x != first]:
            body = {"model": m, "voice": tv["oai"], "input": text, "response_format": "mp3"}
            if m != "tts-1":
                body["instructions"] = style
            req = urllib.request.Request(TTS_URL, json.dumps(body).encode(), {"Authorization": "Bearer " + (key or ""),
                                                                               "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                if not raw or raw[:1] in (b"{", b"<"):
                    last = "empty"
                    break
                try:
                    tmp = fp + ".part"
                    with open(tmp, "wb") as f:
                        f.write(raw)
                    os.replace(tmp, fp)
                    self._tts_n += 1
                    if self._tts_n % 50 == 0:              # keep the newest 800 sentences
                        d = self._tts_dir()
                        files = sorted((os.path.getmtime(os.path.join(d, x)), x) for x in os.listdir(d) if x.endswith(".mp3"))
                        for _, x in files[:-800]:
                            try:
                                os.remove(os.path.join(d, x))
                            except OSError:
                                pass
                except OSError:
                    pass
                return raw, self._tts_cost(c, text, m), False, None
            except urllib.error.HTTPError as e:
                try:
                    msg = str((json.loads(e.read().decode() or "{}").get("error") or {}).get("message") or "")[:200]
                except Exception:
                    msg = ""
                last = ("%s %s" % (e.code, msg)).strip()
                if e.code in (400, 403, 404) and "model" in msg.lower():
                    continue                               # a speech model this account does not have: the next one
                break
            except Exception as e:
                last = str(e)[:200]
                break
        why = ("مفتاح OpenAI ما يسمح بنموذج الصوت أو رصيده خلص" if last[:3] in ("401", "402", "403", "429")
               else "OpenAI ما قرأ الرد بصوت")
        return None, 0.0, False, (why, last)

    def _multipart(self, url, key, fields, fname, data, ctype, timeout=30):
        b = "----gm" + secrets.token_hex(12)
        ctype = re.sub(r"[^\w/.+-]", "", ctype or "")[:40] or "application/octet-stream"
        parts = [('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v)).encode() for k, v in fields.items()]
        parts.append(('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\nContent-Type: %s\r\n\r\n'
                      % (b, fname, ctype)).encode() + data + b"\r\n")
        parts.append(("--%s--\r\n" % b).encode())
        req = urllib.request.Request(url, b"".join(parts), {"Authorization": "Bearer " + (key or ""),
                                                            "Content-Type": "multipart/form-data; boundary=" + b})
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

    def _stt(self, raw, mime, c):
        """His recorded sentence -> text (OpenAI, the shop's key): (text, problem, model)."""
        key = self.agent.cfg().get("api_key")
        base = (mime or "").split(";")[0].strip().lower()
        ext = {"audio/webm": "webm", "video/webm": "webm", "audio/mp4": "mp4", "video/mp4": "mp4", "audio/x-m4a": "m4a",
               "audio/m4a": "m4a", "audio/aac": "m4a", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/wav": "wav",
               "audio/x-wav": "wav"}.get(base, "webm")
        first = c.get("stt_model") or "gpt-4o-mini-transcribe"
        last = ""
        for m in [first] + [x for x in ("gpt-4o-mini-transcribe", "gpt-transcribe", "whisper-1") if x != first]:
            code, d = self._multipart(STT_URL, key, {"model": m, "language": "ar", "response_format": "json", "prompt": STT_PROMPT},
                                      "speech." + ext, raw, base or "audio/webm")
            if code == 200:
                return str(d.get("text") or "").strip(), None, m
            msg = str((d.get("error") or {}).get("message") or "")[:200]
            last = ("%s %s" % (code, msg)).strip()
            if code in (400, 403, 404) and "model" in msg.lower():
                continue                           # a model this account does not have: the next one
            break
        return "", last or "ما قدرنا نحوّل الكلام لكتابة", first

    def _log_turn(self, who, session, ip, kind, stt_s, stt_cost, chars, credits, tts_cost, backend, cached, lab, buyer, ms, err):
        with self.lock, self.app.lock:
            self.store.db.execute("INSERT INTO voice_turns (visitor,session,ip,day,ts,kind,stt_s,stt_cost,chars,credits,tts_cost,"
                                  "backend,cached,lab,buyer,ms,err) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (who, session, (ip or "")[:60], self._today(), time.time(), kind, round(stt_s, 2), stt_cost,
                                   int(chars), round(credits, 1), tts_cost, backend, 1 if cached else 0, 1 if lab else 0,
                                   1 if buyer else 0, int(ms or 0), (err or None) and str(err)[:200]))
            self.store.db.commit()

    def _say(self, c, tv, who, session, ip, lab, t0, kind, say, out, stt_cost, stt_s, buyer, ms):
        audio, cost, cached, err = self._tts(say, tv, c)
        tts_cost = round(cost, 6)
        credits = 0.0
        backend = self._backend_cost(session, t0, time.time()) if kind == "turn" else 0.0
        self._log_turn(who, session, ip, kind, stt_s, stt_cost, 0 if cached else len(say), credits, tts_cost, backend,
                       cached, lab, buyer, ms, err and err[1])
        if err:
            self._warn(0, err[1], why="الصوت «رد ورد»: " + err[0])
        conv = self.store.one("SELECT COALESCE(SUM(stt_cost+tts_cost+backend),0) c FROM voice_turns WHERE day=? AND session=?",
                              (self._today(), session))["c"]
        res = dict(out, ok=True, say=say, turn_usd=round(stt_cost + tts_cost + backend, 5), conv_usd=round(float(conv or 0), 5),
                   today_usd=round(self._spent_voice_today(), 5))
        if audio:
            res["audio"], res["mime"] = base64.b64encode(audio).decode(), "audio/mpeg"
        elif err and (lab or c.get("test_mode")):
            res["detail"] = "الصوت ما اشتغل، " + err[0]
        return res

    def turn(self, visitor, session, audio_b64, mime, ms, ip, lab, picks=None, hello=False, voice=None):
        """One sentence from the phone -> the shop assistant's answer, said in OpenAI's voice."""
        c = self.cfg()
        tv = TURN_BY_ID.get(voice or "") or TURN_BY_ID.get(c.get("voice")) or TURN_VOICES[0]
        session = re.sub(r"[^A-Za-z0-9_-]", "", session or "")[:40]
        if not session:
            return {"ok": False, "why": "bad"}
        who = self._who(visitor, ip)
        show = bool(lab or c.get("test_mode"))
        st = self.status(visitor, ip, lab)
        if not st["on"]:
            why = {"hidden": "الصوت موقّف من لوحة الإدارة", "off": "المساعد مطفي أو ما فيه مفتاح", "monthly": "الحد الشهري خلص",
                   "daily": "حد الصوت اليومي خلص", "customer": "حد هذا الزبون اليومي خلص"}.get(st.get("why"), st.get("why") or "")
            return {"ok": False, "why": st.get("why"), "say": BUSY, "detail": why if show else ""}
        t0 = time.time()
        if hello:
            # a few greetings, picked at random: each is made once and kept, so after the first time they cost nothing
            text = secrets.choice(HELLO_BACK if self._history(session, 2) else HELLO_T)
            if tv.get("g") == "f":
                text = text.replace("أنا مستشارك", "أنا مستشارتك").replace("معك مستشار ", "معك مستشارة ")
            return self._say(c, tv, who, session, ip, lab, t0, "hello", text, {"text": text}, 0.0, 0.0, False, 0)
        try:
            raw = base64.b64decode(audio_b64 or "", validate=False)
        except Exception:
            raw = b""
        if len(raw) > 1_100_000:
            return {"ok": False, "why": "bad"}
        try:
            ms = max(0, min(60000, int(ms or 0)))
        except (TypeError, ValueError):
            ms = 0
        if len(raw) < 600:                          # nothing real was recorded
            return self._say(c, tv, who, session, ip, lab, t0, "misheard", MISHEARD, {"text": MISHEARD, "misheard": True},
                             0.0, 0.0, False, ms)
        dur = max(0.5, min(float(c["turn_max_s"]) + 5, (ms / 1000.0) or len(raw) / 4000.0))
        heard, err, model = self._stt(raw, mime, c)
        stt_cost = round(dur / 60.0 * float(c["stt_per_min"]), 6)
        an = getattr(self.agent, "analytics", None)
        if an:   # turning his words into text is paid to OpenAI: it counts in the same monthly cap
            try:
                an.log_ai(session, model, "voice", "voice", "voice:stt", 0, 0, 0, stt_cost, int((time.time() - t0) * 1000), "")
            except Exception:
                pass
        if err:
            self._warn(0, err, why="تحويل كلام الزبون لكتابة ما اشتغل")
            out = {"text": "صار عندي خلل بسيط في السماع، ممكن تعيد كلامك؟", "misheard": True, "heard": ""}
            if show:
                out["detail_stt"] = err
            return self._say(c, tv, who, session, ip, lab, t0, "stt_err", out["text"], out, stt_cost, dur, False, ms)
        clean = re.sub(r"[\s.,،!?؟…\-]+", " ", heard).strip()
        if len(clean) < 2 or JUNK.search(heard) or not re.search(r"[؀-ۿ0-9]", heard):
            return self._save_misheard(c, tv, who, session, ip, lab, t0, stt_cost, dur, ms, heard)
        vis = who if not who.startswith("ip:") else None
        res = (self.agent.chat(session, heard, vis, picks) if picks is not None else self.agent.chat(session, heard, vis)) or {}
        buyer = bool(res.get("offer")) or res.get("stage") in ("ready", "closing")
        say = speakable(res.get("text") or "", int(c["tts_max_chars"])) or "خلني أتأكد لك وأرجع لك."
        out = {"heard": heard, "text": res.get("text") or "", "pieces": res.get("pieces") or [], "suggest": res.get("suggest") or []}
        for k in ("offer", "handoff", "add_picks"):
            if k in res:
                out[k] = res[k]
        return self._say(c, tv, who, session, ip, lab, t0, "turn", say, out, stt_cost, dur, buyer, ms)

    def _save_misheard(self, c, tv, who, session, ip, lab, t0, stt_cost, dur, ms, heard):
        out = {"text": MISHEARD, "misheard": True, "heard": ""}
        if lab or c.get("test_mode"):
            out["junk"] = heard[:80]
        return self._say(c, tv, who, session, ip, lab, t0, "misheard", MISHEARD, out, stt_cost, dur, False, ms)

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
        tr = self.store.q("SELECT * FROM voice_turns WHERE day BETWEEN ? AND ? ORDER BY id DESC", (a, b))
        turns = {"turns": sum(1 for r in tr if r["kind"] == "turn"), "talks": len({r["session"] for r in tr if r["kind"] != "test"}),
                 "chars": sum(int(r["chars"] or 0) for r in tr), "credits": round(sum(float(r["credits"] or 0) for r in tr)),
                 "stt": round(sum(float(r["stt_cost"] or 0) for r in tr), 4), "tts": round(sum(float(r["tts_cost"] or 0) for r in tr), 4),
                 "backend": round(sum(float(r["backend"] or 0) for r in tr), 4), "cached": sum(1 for r in tr if r["cached"]),
                 "errors": sum(1 for r in tr if r["err"]), "last_error": next((r["err"] for r in tr if r["err"]), "")}
        turns["cost"] = round(turns["stt"] + turns["tts"] + turns["backend"], 4)
        return {"totals": tot, "recent": recent, "today": round(self._spent_voice_today(), 4),
                "caps": {"customer": c["per_customer_usd"], "buyer": c["buyer_usd"], "day": c["daily_usd"]},
                "price_per_min": c["price_per_min"], "public": c["public"], "test_mode": bool(c.get("test_mode")),
                "turns": turns}

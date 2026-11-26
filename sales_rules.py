# -*- coding: utf-8 -*-
"""The sales agent's fixed rules, kept outside the model: free, instant and testable without any AI.

  route()        sorts each customer message (greeting, location, gold price, policy question, piece request...)
  answer()       ready answers for the common questions, from the shop's own facts (no model, no cards)
  moment()       the one instruction the model gets for this reply (just in time, not a thousand rules at once)
  check_reply()  every model reply is checked before it is sent: numbers, promises, scarcity, taste, piece type,
                 banned words, repeats, questions, number of pieces

Built from the Nov 2026 research on how large retailers run sales agents (Amazon Rufus, Shopify Sidekick,
Salesforce Agentforce, Klarna, Chow Tai Fook, Anthropic's Project Vend, tau-bench): the model talks, the system
knows. Tested in tests/agent_rules_test.py.
"""
import difflib
import re

_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
                     "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
                     "٬": ",", "٫": "."})


def norm(t):
    t = re.sub(r"[ً-ْـ]", "", (t or "").lower())
    return t.translate(_AR)


_EDGE = r"(?:^|(?<=[\s،,.؟?!:؛\"'()]))"
_END = r"(?=$|[\s،,.؟?!:؛\"'()])"


def _rx(words, suffix=True):
    """Whole words (with the usual و/ف/ب/ل/ال in front and, by default, any ending) — not pieces of other words."""
    alts = []
    for w in words:
        w = norm(w)
        alts.append(r"(?:و|ف|ب|ل|ك)?(?:ال|لل)?" + re.escape(w) + (r"\w*" if suffix else ""))
    return re.compile(_EDGE + "(?:" + "|".join(sorted(alts, key=len, reverse=True)) + ")" + _END)


# ---------------------------------------------------------------- what a message is about
WORDS = {
    "greet": ["السلام عليكم", "السلام", "سلام", "مرحبا", "مرحبتين", "هلا", "اهلين", "اهلا", "صباح الخير", "مساء الخير",
              "صباح النور", "مساء النور", "هاي", "هلو", "حياكم"],
    "thanks": ["شكرا", "مشكور", "مشكورين", "يعطيك العافيه", "يعطيكم العافيه", "تسلم", "تسلمون", "جزاك الله", "جزاكم الله",
               "الله يعطيك", "ما قصرت", "ما قصرتوا", "يسلمو"],
    "bye": ["مع السلامه", "باي", "في امان الله", "الله يحفظك", "استودعك الله"],
    "location": ["وين", "فين", "وينكم", "فينكم", "عنوان", "عنوانكم", "موقعكم", "مكانكم", "لوكيشن", "الخريطه", "فروع",
                 "فرعكم", "مقركم", "اين"],
    "hours": ["متى تفتحون", "متى تفتح", "متى تقفلون", "متى تقفل", "متى تسكرون", "الدوام", "دوامكم", "مفتوحين",
              "فاتحين", "تفتحون", "اوقات العمل", "اوقاتكم", "مواعيدكم", "متى الدوام", "تفتحون الجمعه"],
    "gold_price": ["سعر الجرام", "سعر جرام", "سعر الذهب", "اسعار الذهب", "كم الجرام", "الجرام بكم", "الجرام كم",
                   "كم سعر الذهب", "كم الذهب", "سعر الجنيه", "الجنيه بكم", "كم الجنيه", "جرام 21", "سعر 21"],
    "karat": ["عيار 18", "عيار18", "عيار 24", "عيار24", "عيار 22", "كم عيار", "اي عيار", "ايش العيار", "وش العيار",
              "ذهب 18", "ذهب 24", "18 قيراط", "24 قيراط", "عيار كم", "عياره", "عيارها", "الذهب حقكم كم", "العيار"],
    "returns": ["ارجعه", "ارجعها", "ارجاع", "استرجاع", "استرداد", "ترجعونه", "ترجعونها", "ترجعون", "ترجيع",
                "ارجع القطعه", "ارد القطعه", "ينرد", "ترجع الفلوس", "ارجعها لكم", "ارجّعها"],
    "trade_in": ["ابدل", "استبدال", "تبديل", "ابادل", "ذهبي القديم", "ذهب قديم", "اغير ذهبي", "تبدلون", "تبادلون",
                 "بدل ذهبي", "ابدله", "ابدلها"],
    "repairs": ["تصلح", "تصلحون", "تصليح", "صيانه", "تلحيم", "تلحمون", "انكسر", "انقطع", "تعديل مقاس", "تكبير",
                "تصغير", "تكبرون", "تصغرون", "تلميع"],
    "sell_gold": ["ابيع ذهب", "ابغى ابيع", "ابي ابيع", "ابيع ذهبي", "تشترون ذهب", "تشترون الذهب", "عندي ذهب ابيعه",
                  "ابيع كسر", "تشترون كسر", "تشترون مني", "ابيع لكم", "ابيعكم"],
    "price_lock": ["ثبت السعر", "ثبت لي السعر", "ثبتلي السعر", "تثبيت السعر", "تثبتون السعر", "تثبت السعر",
                   "يثبت السعر", "ثبتوا السعر", "تثبت لي", "ثبت لي سعرها", "ثبت لي سعره", "بنفس السعر بكره"],
    "deposit": ["عربون", "احجز", "احجزها", "احجزه", "الحجز", "حجز", "تحجز", "تحجزون", "تحجزوها", "حجزها"],
    "instalments": ["تقسيط", "اقساط", "قسط", "دفعات", "على دفعات", "اقسطها", "تقسطون"],
    "pay_later": ["ادفع بعدين", "ادفع بكره", "الدفع بعدين", "بالاجل", "اجل", "ادفع لاحقا", "الباقي بعدين",
                  "اسلم الباقي", "بعد الراتب", "ادفع نص"],
    "discount": ["خصم", "تخفيض", "تخفيضات", "خصومات", "تنزل لي", "تنزلون لي", "نزل لي", "نزلي", "تنزل من السعر",
                 "اخر سعر", "كم اخر", "تراعيني", "راعني", "سعر خاص", "ما تنزل"],
    "complaint": ["شكوى", "اشتكي", "نصب", "نصابين", "غش", "غشاشين", "مغشوش", "زعلان", "زعلانين", "تعامل سيء",
                  "سيئين", "خدمه سيئه", "ما رديتوا", "ما احد يرد", "مقهور", "حراميه", "احتيال", "ظلمتوني"],
    "human": ["اكلم شخص", "اكلم احد", "اكلم موظف", "ابغى موظف", "ابي موظف", "ابغى انسان", "ابي انسان",
              "شخص حقيقي", "انسان حقيقي", "اكلم المبيعات", "ابغى اكلم", "ابي اكلم", "رقمكم", "رقم الواتساب",
              "رقم واتساب", "واتسابكم", "اتصل فيكم", "رقم المحل", "رقم التلفون", "اكلم المحل", "مدير المحل",
              "صاحب المحل", "تواصل معكم", "اتواصل معكم"],
    "bot_q": ["انت انسان", "انت بوت", "انت روبوت", "انت حقيقي", "ذكاء اصطناعي", "بشر ولا", "انت بشر", "مين انت",
              "من انت", "انت ايش", "مين معي", "منو معي"],
    "forecast": ["بيطلع", "بينزل", "بيرتفع", "بينخفض", "يطلع ولا ينزل", "يرتفع ولا", "الذهب رايح", "توقعاتك",
                 "تتوقع", "تنصحني انتظر", "انتظر ينزل", "متى ينزل الذهب", "الذهب نازل", "الذهب طالع"],
    "competitor": ["محل ثاني", "المحل الثاني", "محلات ثانيه", "عند غيركم", "غيركم ارخص", "ارخص عند", "ارخص منكم",
                   "السوق ارخص", "عند فلان", "محل فلان", "جيرانكم"],
    "account": ["رقم حساب", "رقم الحساب", "ارقام الحساب", "حسابكم", "احول على", "احول لكم", "احولكم", "حساب بنكي",
                "الكريمي", "رقم الحواله", "ايبان", "iban", "محفظه"],
    "injection": ["انس التعليمات", "انسى التعليمات", "انسى كل", "انس كل", "تجاهل التعليمات", "تجاهل كل", "system prompt",
                  "البرومبت", "برومبت", "تعليماتك", "التعليمات الداخليه", "كلمه السر", "باسورد", "password",
                  "لوحه التحكم", "المصنعيه الداخليه", "سعر التكلفه", "تكلفه القطعه", "كم ربحكم", "هامش الربح",
                  "كم تكسبون"],
    # selling signals
    "misunderstood": ["ما فهمت", "مو فاهم", "ما فهمتني", "ما فهمت علي", "مو هذا", "مو قصدي", "مش قصدي", "قلت لك",
                      "قلتلك", "مو كذا", "ما طلبت كذا", "انا قلت", "ركز", "ما قلت كذا"],
    "thinking": ["بفكر", "افكر", "بشاور", "اشاور", "برجع لك", "بعدين ارد", "خلني افكر"],
    "obj_price": ["غالي", "غاليه", "غالين", "مره غالي", "كثير عليها", "فوق ميزانيتي", "ما معي", "ما عندي فلوس",
                  "السعر كثير", "سعرها كثير"],
    "making": ["المصنعيه", "مصنعيه", "مصنعيتها", "مصنعيته", "الصنعه", "اجره الصنعه"],
    "ready": ["ابغاه", "ابيه", "اخذه", "ابغاها", "ابيها", "اخذها", "كيف اشتري", "كيف اشتريها", "اشتريها", "اشتريه",
              "كيف ادفع", "كيف احول", "متى استلم", "تمام ابغى", "خلاص ابغى", "ابغى الاول", "ابغى الثاني",
              "ابي الاول", "اعتمدها", "اعتمده", "خلاص هذي", "خلاص هذا"],
    "browse_strong": ["وريني", "ورني", "اعرض لي", "اعرضلي", "اقترح", "وش عندكم", "ايش عندكم", "الجديد", "جديد",
                      "تشكيله", "موديلات", "صور"],
    "browse": ["ابغى", "ابي", "اريد", "عندكم", "ادور", "اشوف", "عطني", "فيه", "تبيعون", "ابحث"],
    "currency": ["سعودي", "ريال سعودي", "دولار", "usd", "sar"],
}
RX = {k: _rx(v) for k, v in WORDS.items()}
# words that are a mother/sister/wife... used without endings (so "امكان" is never "امك")
RELATIVES = _rx(["اختك", "امك", "زوجتك", "بنتك", "خالتك", "عمتك", "حرمتك", "مرتك", "مدام", "المدام", "والدتك",
                 "خطيبتك", "اهلك", "بنت عمك", "الزوجه", "زوجه"], suffix=False)

KIND_WORDS = {"طقم": ["طقم", "اطقم", "طقوم", "شبكه"], "عقد": ["عقد", "قلاده", "عقود", "كردان", "كردانات"],
              "حلق": ["حلق", "اقراط", "قرط"], "خاتم": ["خاتم", "خواتم", "دبله", "محبس"],
              "أسورة": ["اسوره", "اساور", "غويش", "بنجري", "سوار"], "كف": ["كف", "كفوف"], "حزام": ["حزام", "احزمه"],
              "سلسلة": ["سلسله", "سلاسل", "تعليقه"], "جنيه": ["جنيه", "جنيهات", "ليره", "سبيكه"]}
OCC_WORDS = {"عرس": ["عرس", "زواج", "زفاف", "عروس", "عروسه", "ملكه"], "خطوبة": ["خطوبه", "شبكه", "مخطوبه"],
             "هدية": ["هديه", "هدايا", "عيد ميلاد"], "يومي": ["يومي", "للدوام", "للشغل", "استخدام يومي", "خفيف"]}
RX_KIND = _rx(sum(KIND_WORDS.values(), []))
RX_OCC = _rx(sum(OCC_WORDS.values(), []))
RX_BUDGET = re.compile(r"\d[\d,.]*\s*(مليون|الف|ريال|سعودي|دولار|\$)|ميزاني|بحدود|حدود\s*\d|اقل من\s*\d|\d+\s*(جرام|جم|غرام)")
RX_CODE = re.compile(r"(?<![a-z])[a-z]?\d{5,7}(?![\d])")
RX_ORDINAL = re.compile(_EDGE + r"(?:ال|لل)?(اول|ثاني|ثالث|رابع|اخير)(?:ه|ي)?" + _END)

FAQ = ("greet", "thanks", "bye", "location", "hours", "gold_price", "karat", "returns", "trade_in", "repairs",
       "sell_gold", "price_lock", "deposit", "instalments", "pay_later", "discount", "complaint", "human", "bot_q",
       "forecast", "competitor", "account", "injection")
# a question that ends the conversation's selling turn: the shop's rule, and a person from the sales team
TERMINAL = ("injection", "complaint", "human", "discount", "account")
POLICY = ("karat", "returns", "trade_in", "repairs", "price_lock", "deposit", "instalments", "pay_later", "sell_gold")
NO_OFFER = ("thanks", "bye", "human", "bot_q", "complaint", "account", "discount")
LABEL = {"greet": "رد السلام", "thanks": "الشكر", "bye": "الوداع", "location": "مكان المحل", "hours": "الدوام",
         "gold_price": "سعر الذهب", "karat": "العيار", "returns": "الإرجاع", "trade_in": "التبديل", "repairs": "التصليح",
         "sell_gold": "بيع الذهب للمحل", "price_lock": "تثبيت السعر", "deposit": "الحجز", "instalments": "التقسيط",
         "pay_later": "الدفع لاحقاً", "discount": "الخصم", "complaint": "الشكوى", "human": "طلب موظف",
         "bot_q": "سؤال هل هو بوت", "forecast": "توقع سعر الذهب", "competitor": "مقارنة بمحل ثاني",
         "account": "رقم الحساب", "injection": "طلب بيانات داخلية"}


def route(text, shown=False, ref=None):
    """-> {"intents": [...in the order they appear], "faq": [...], "selling": [...], "path": "template"|"llm",
    "words": n, "kinds": [...], "occasions": [...]}"""
    t = " " + norm(text).strip() + " "
    words = len(t.split())
    hits = []
    for name, rx in RX.items():
        m = rx.search(t)
        if m:
            hits.append((m.start(), name))
    hits.sort()
    intents = [n for _, n in hits]
    kinds = [k for k, ws in KIND_WORDS.items() if _rx(ws).search(t)]
    occ = [k for k, ws in OCC_WORDS.items() if _rx(ws).search(t)]
    # «وين» alone is the shop's place; «وين القطعة الأولى» is not
    if "location" in intents and (kinds or ref or RX_ORDINAL.search(t) or "قطع" in t) and \
            not re.search("عنوان|موقعكم|مكانكم|لوكيشن|فروع|فرع", t):
        intents.remove("location")
    if "karat" in intents and not re.search(r"18|22|24|كم|(^|\s)اي\s|ايش|وش|عندكم|فيه|؟|\?", t):
        intents.remove("karat")             # «أبغى طقم عيار 21» is a request, not a question about karats
    if "greet" in intents and "سلام" in t and "bye" in intents and "مع السلامه" in t:
        intents.remove("greet")
    if "returns" in intents and "ارجع" in t and RX_ORDINAL.search(t):     # «ارجع للأول» is going back, not a return
        intents.remove("returns")
    faq = [i for i in intents if i in FAQ]
    browse_words = "browse" in intents
    selling = []
    if kinds and (browse_words or "browse_strong" in intents or not faq):
        selling.append("kind")
    if occ and not (faq and set(faq) <= set(POLICY) and not browse_words):
        selling.append("occasion")
    if RX_BUDGET.search(t) and not ("karat" in faq and not browse_words):
        selling.append("budget")
    if ref or RX_CODE.search(t) or (shown and RX_ORDINAL.search(t)):
        selling.append("piece")
    for s in ("browse_strong", "ready", "obj_price", "making", "thinking", "misunderstood", "currency"):
        if s in intents and (s not in ("thinking", "misunderstood", "obj_price") or shown):
            if s == "currency" and not (shown or kinds or re.search(r"\d", t) or "ميزاني" in t):
                continue             # «كم الساعة في السعودية» is not about money
            selling.append(s)
    if "browse" in intents and not faq:
        selling.append("browse")
    if "injection" in faq:
        path, faq = "template", ["injection"]
    elif any(i in TERMINAL for i in faq):
        path = "template"
        faq = [i for i in faq if i in TERMINAL or i in ("greet",)]
    elif faq and not selling and (words <= 14 or (len(faq) >= 2 and words <= 22)):
        alone = set(faq) <= {"greet", "thanks", "bye"}
        path = "template" if (not alone or words <= 6) else "llm"
    else:
        path = "llm"
    return {"intents": intents, "faq": faq, "selling": selling, "path": path, "words": words, "kinds": kinds,
            "occasions": occ}


# ---------------------------------------------------------------- ready answers (the shop's facts, never invented)
def _hours_short(h):
    s = re.sub(r"^\s*(المحل|محلنا)\s+(يفتح|مفتوح|يستقبلكم|يستقبلك)\s+", "", (h or "").strip()).strip().rstrip(".")
    return s or (h or "").strip().rstrip(".")


def _first(text, n=2):
    parts = re.split(r"(?<=[.!؟])\s+", (text or "").strip())
    return " ".join(parts[:n]).strip()


def _money(v):
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return ""


def _pick(options, k):
    return options[k % len(options)]


def _a(intent, f, t, k, all_intents):
    """-> (text, closing line or None, flags)"""
    name, addr = f.get("name") or "جمال المشرقي للذهب والمجوهرات", f.get("address") or ""
    hs = _hours_short(f.get("hours"))
    pr = f.get("prices") or {}
    at = f.get("price_time") or ""
    visit = f"وإذا تحب تشوف القطعة بنفسك، محلنا {addr}، ونستقبلك {hs}." if addr else None
    if intent == "greet":
        if "سلام" in t:
            return _pick(["وعليكم السلام، حياك الله في جمال المشرقي.", "وعليكم السلام ورحمة الله، يا هلا فيك.",
                          "وعليكم السلام، أهلاً وسهلاً فيك."], k), "تدور على شي لمناسبة معينة، ولا تحب تشوف الجديد؟", {}
        return _pick(["هلا والله، حياك الله في جمال المشرقي.", "يا هلا فيك، حياك الله.", "أهلاً وسهلاً، حياك الله."], k), \
            "تدور على شي لمناسبة معينة، ولا تحب تشوف الجديد؟", {}
    if intent == "thanks":
        if f.get("shown"):
            return _pick(["العفو، وإذا حبيت أي وحدة من اللي شفتها قل لي.", "الله يحييك، وأنا موجود إذا احتجت شي."], k), None, {}
        return _pick(["العفو، حياك الله في أي وقت.", "الله يحييك، بالخدمة في أي وقت."], k), None, {}
    if intent == "bye":
        return (f"في أمان الله. محلنا {addr}، ونستقبلك {hs}." if addr else "في أمان الله، حياك الله في أي وقت."), None, {}
    if intent == "location":
        tail = "" if "hours" in all_intents else f" ونستقبلك {hs}."
        return f"محلنا {name}، {addr}.{tail}", "وإذا تحب تشوف القطع قبل ما توصل، قل لي وش تدور عليه وأعرضها لك هنا.", {}
    if intent == "hours":
        return f"نستقبلك {hs}.", None, {}
    if intent == "gold_price":
        if not pr.get("k21_sell"):
            return "أسعار اليوم ما تحدثت للحين.", "فريق المبيعات يعطيك السعر الحين على الواتساب، الزر تحت.", {"handoff": True}
        if f.get("price_today", True):
            txt = f"سعر بيع جرام الذهب عيار 21 اليوم {_money(pr['k21_sell'])} ريال يمني" + (f" (آخر تحديث {at})." if at else ".")
        else:            # never call an old price "today's"
            txt = (f"آخر سعر مسجل لبيع جرام الذهب عيار 21: {_money(pr['k21_sell'])} ريال يمني" + (f" (بتاريخ {at})" if at else "") +
                   "، والسعر النهائي بسعر يوم الشراء.")
        if pr.get("pound_sell"):
            txt += f" والجنيه الذهب بـ{_money(pr['pound_sell'])} ريال."
        if pr.get("k21_buy") and "sell_gold" not in all_intents:
            txt += f" ولو حاب تبيع ذهبك، نشتري الجرام بـ{_money(pr['k21_buy'])} ريال."
        return txt, "وأقدر أحسب لك سعر أي قطعة بالوزن والمصنعية.", {}
    if intent == "karat":
        return "ذهبنا كله عيار 21، ومعه جنيهات ذهب. ما عندنا عيار 18 ولا 24.", None, {}
    if intent == "returns":
        txt = _first(f.get("returns")) or "البيع نهائي: ما فيه إرجاع ولا استبدال بعد الشراء."
        return txt, "وإذا تحب، أساعدك تتأكد من الوزن والشكل والصور قبل ما تقرر.", {}
    if intent == "trade_in":
        return ("ما نسوي تبديل ذهب بذهب. وإذا حاب تبيع ذهبك، المحل يشتريه بسعر شراء اليوم بعد الفحص والوزن قدامك."), None, {}
    if intent == "repairs":
        return _first(f.get("warranty"), 1) or "المحل يتاجر في الذهب فقط، وما عنده خدمة تصليح.", None, {}
    if intent == "sell_gold":
        buy = f" بسعر شراء اليوم ({_money(pr['k21_buy'])} ريال لجرام عيار 21)" if pr.get("k21_buy") else " بسعر شراء اليوم"
        txt = f"شراء الذهب من الزبائن يكون في المحل مباشرة: الموظف يفحصه ويوزنه قدامك{buy}."
        if addr and "location" not in all_intents:
            txt += f" محلنا {addr}، ونستقبلك {hs}."
        return txt, None, {}
    if intent == "price_lock":
        return "البيع عندنا بسعر الذهب ساعة الشراء، يد بيد، فما نثبت سعر ليوم ثاني.", visit, {}
    if intent == "deposit":
        d = f.get("deposit") or {}
        if d.get("enabled"):
            return (f"الحجز بعربون {_money(d.get('pct'))}% يكون من صفحة القطعة، ويحفظها {_money(d.get('hours'))} ساعة بس، "
                    "وما يثبت السعر: السعر النهائي بسعر الذهب يوم الشراء."), visit, {}
        return "ما نشتغل بالحجز، البيع بسعر الذهب يوم الشراء.", visit, {}
    if intent == "instalments":
        return "ما فيه تقسيط ولا دفعات، البيع بسعر اليوم ويندفع كامل.", visit, {}
    if intent == "pay_later":
        return "ما فيه آجل ولا دفع بعدين، البيع يد بيد بسعر اليوم.", visit, {}
    if intent == "bot_q":
        return ("أنا مساعد آلي لمحل جمال المشرقي: أعرف القطع المتوفرة وأسعارها اليوم. "
                "وإذا تحب تكلم شخص من فريق المبيعات، الزر تحت."), None, {"handoff": True}
    if intent == "human":
        return "أكيد، فريق المبيعات يكمل معك على الواتساب، اضغط الزر تحت.", None, {"handoff": True}
    if intent == "discount":
        return ("الأسعار عندنا محسوبة بسعر الذهب اليوم × الوزن + المصنعية، وما أقدر أعطي خصم من هنا. "
                "إذا تحب تتفاهم على المصنعية، فريق المبيعات يكمل معك على الواتساب (الزر تحت)."), None, {"handoff": True}
    if intent == "complaint":
        return ("آسفين على اللي صار. خلني أوصلك بفريق المبيعات على الواتساب مباشرة عشان يحلون الموضوع معك."), None, \
            {"handoff": True, "alert": True}
    if intent == "forecast":
        if pr.get("k21_sell"):
            day = "اليوم" if f.get("price_today", True) else "المسجل"
            when = f" ({'آخر تحديث' if f.get('price_today', True) else 'بتاريخ'} {at})" if at else ""
            return (f"ما أقدر أتوقع حركة الذهب. اللي أعرفه أكيد: سعر بيع جرام 21 {day} {_money(pr['k21_sell'])} ريال{when}، "
                    "والبيع عندنا بسعر يوم الشراء."), None, {}
        return "ما أقدر أتوقع حركة الذهب، والبيع عندنا بسعر يوم الشراء.", None, {}
    if intent == "competitor":
        if pr.get("k21_sell") and "gold_price" not in all_intents:
            txt = (f"حقك تقارن، بس قارن على نفس الأساس: العيار، والوزن، والمصنعية. سعرنا = سعر جرام 21 يوم الشراء "
                   f"({'اليوم' if f.get('price_today', True) else 'آخر سعر مسجل'} {_money(pr['k21_sell'])}) × الوزن + المصنعية المكتوبة لكل قطعة.")
        else:
            txt = "حقك تقارن، بس قارن على نفس الأساس: العيار، والوزن، والمصنعية."
        return txt, ("وأقدر أفصّل لك حساب أي قطعة شفتها." if f.get("shown") else "وإذا تبغى، أحسب لك سعر أي قطعة تعجبك بالتفصيل."), {}
    if intent == "account":
        return ("أرقام الحسابات تظهر لك في صفحة القطعة بعد ما توافق على شروط الشراء، "
                "أو يعطيك إياها فريق المبيعات على الواتساب (الزر تحت)."), None, {"handoff": True}
    if intent == "injection":
        return "هذا شي ما أقدر أشاركه.", "أقدر أساعدك تلقى قطعة تناسبك، أو أعطيك سعر الذهب اليوم.", {}
    if intent == "consent_yes":
        return "تمام، حفظت طلبك. وإذا رجعت أطلع لك الجديد عليه على طول.", None, {"consent": True}
    if intent == "consent_no":
        return "ولا يهمك، حياك الله في أي وقت.", None, {}
    return "", None, {}


def answer(intents, f, k=0, text="", closing=True):
    """Ready answer for the common questions in one message, in the order asked; one closing line at most and
    never more than one question. f: the shop's facts (see agent.SalesAgent._facts)."""
    t = norm(text)
    seen, parts, flags = [], [], {}
    close = None
    for i in intents:
        if i in seen:
            continue
        seen.append(i)
        txt, c, fl = _a(i, f, t, k, intents)
        if txt:
            parts.append(txt)
        for key, v in fl.items():
            flags[key] = flags.get(key) or v
        if c:
            close = c
    if any(i in NO_OFFER for i in seen):
        close = None
    elif not close and closing and not set(seen) <= {"thanks", "bye", "consent_yes", "consent_no"}:
        close = "تحب نكمل على القطع اللي شفتها؟" if f.get("shown") else "تدور على شي لمناسبة معينة؟"
    if f.get("consent_ask") and set(seen) & {"thanks", "bye"}:
        close = f"تحب أحفظ طلبك ({f['consent_ask']}) عشان لو رجعت أطلع لك الجديد عليه على طول؟"
        flags["consent_asked"] = True
    out = " ".join(parts)
    if close and closing:
        if "؟" in close:
            out = out.replace("؟", ".")
        out = (out + "\n" + close).strip()
    return out.strip(), flags


YES = _rx(["ايوه", "ايوا", "اي", "اكيد", "نعم", "تمام", "ياليت", "اوكي", "طيب", "احفظه", "احفظ", "موافق", "يب", "ok"])
NO = _rx(["لا", "لا شكرا", "مو لازم", "ما ابغى", "ما ابي", "خلاص لا", "لاتحفظ", "لا تحفظ"])


def consent_reply(text):
    t = " " + norm(text).strip() + " "
    if len(t.split()) > 6:
        return None
    if NO.search(t):
        return "consent_no"
    if YES.search(t):
        return "consent_yes"
    return None


# ---------------------------------------------------------------- the instruction for this moment
SLOT_Q = {"occasion": "المناسبة (عرس، خطوبة، هدية، أو للاستخدام اليومي)",
          "kind": "نوع القطعة (طقم، عقد، سلسلة، حلق، خاتم، أسورة، أو جنيه)",
          "budget": "الميزانية التقريبية أو الوزن اللي في باله"}
PLAYBOOK = {
    "obj_price": ("قال إن السعر غالي: أقر بكلامه بجملة قصيرة، ثم استدعِ price_breakdown للقطعة اللي يقصدها واعرض الحساب "
                  "(سعر جرام 21 اليوم × الوزن + المصنعية)، ثم اعرض بديل أخف بنفس الروح (lighter_than_code أو sort=weight_asc)، "
                  "أو الجنيه إذا يبغى ادخار. لا خصم ولا تلميح له."),
    "making": ("سأل عن المصنعية: استدعِ price_breakdown، واشرح إن المصنعية على شغل هذي القطعة بالذات، "
               "واعرض قطع مصنعيتها أقل إذا يحب. لا خصم من عندك؛ التفاهم على المصنعية مع فريق المبيعات فقط."),
    "thinking": ("قال بيفكر أو بيشاور: احترم، ولخص له بسطر ليش القطعة تناسب طلبه هو، وقل إنه يقدر يرجع لها من صفحتها. "
                 "لا ضغط ولا استعجال ولا ندرة."),
    "currency": "ذكر عملة ثانية: أي سعر بالسعودي أو الدولار من price_breakdown مع currency فقط، ولا تحسب بنفسك.",
    "misunderstood": ("يقول إنك ما فهمته: اعتذر بكلمة وحدة، وأعد طلبه بسطر بكلامه هو، ثم نفّذه بالضبط بالشروط اللي قالها."),
    "ready": "يبغى يشتري: استدعِ offer_purchase للقطعة اللي يقصدها، واكتب سطر واحد يختم.",
}


def moment(r, known, shown, ref=None, pre=None, sold_ref=None, bridal=False, wants_show=False, repeat=0, no_cards=False):
    """The one instruction for this reply (the model reads it last, right before the customer's message).
    -> (text, discovery): discovery = this reply asks one question and shows no pieces."""
    out, discovery = [], False
    if pre:
        out.append("النظام جاوب في بداية الرد على: " + "، ".join(LABEL.get(i, i) for i in pre) + ". لا تعيدها؛ كمل على باقي رسالته.")
    if sold_ref:
        out.append(f"القطعة {sold_ref} انباعت. قلها بصراحة بجملة، واعرض الأقرب لها (search_pieces مع similar_to_code={sold_ref}).")
    if repeat:
        out.append("سأل نفس السؤال قبل: جاوبه بصياغة مختلفة وأوضح، أو اعرض شي جديد فعلاً، ولا تكرر ردك السابق.")
    sel = set(r.get("selling") or [])
    missing = [s for s in ("occasion", "kind", "budget") if not known.get(s)]
    if no_cards:
        out.append("هذا الرد بدون قطع: لا تبحث ولا تكتب أي رمز.")
    elif "ready" in sel and (ref or shown):
        out.append(PLAYBOOK["ready"] + (f" القطعة: [[{ref}]]." if ref else ""))
        if bridal:
            out.append("هذي قطعة مناسبة عرس وهو جاهز يشتري: قل إن فريق المبيعات يكمل معه على الواتساب باسم القطعة (الزر تحت).")
    elif not shown and not wants_show and len(missing) == 3 and not (sel & {"kind", "occasion", "budget", "piece"}):
        discovery = True
        out.append(f"ما نعرف عنه شي للحين: اسأل سؤال واحد بس عن {SLOT_Q['occasion']}. لا تبحث ولا تعرض قطع في هذا الرد."
                   + ("" if r.get("intents") else " وإذا سؤاله ما له علاقة بالذهب أو المحل، قل بلطف إنك مساعد المحل وما عندك هذي "
                                                   "المعلومة، بدون ما تخمّن أي جواب، وبعدها سؤالك."))
    elif not shown and (sel & {"kind", "occasion", "budget", "browse_strong", "browse"} or wants_show):
        if known.get("weight"):
            out.append(f"طلب وزن {known['weight']:g} جم: ابحث بـ near_weight={known['weight']:g}، واعرض الأقرب، وقل الفرق من diff_g "
                       "بالضبط. لا تقل إن وزن قطعة يساوي طلبه إلا إذا diff_g صفر.")
        nxt = next((SLOT_Q[s] for s in missing), None)
        out.append("اعرض قطعتين (ثلاث فقط لسبب واضح) من search_pieces بشروطه"
                   + (f"، وبعدها سؤال واحد بس عن {nxt} إذا يفيد." if nxt and len(missing) >= 2 else "."))
    for key in ("obj_price", "making", "thinking", "currency", "misunderstood"):
        if key in sel:
            out.append(PLAYBOOK[key])
    if not out:
        return "", discovery
    return "## الآن (من النظام، لهذا الرد بالذات)\n" + "\n".join("- " + x for x in out), discovery


# instructions that travel with the tool's answer, exactly when they are needed
TOOL_NOTES = {
    "search_pieces": ("اعرض قطعتين أو ثلاث بالكثير، كل رمز [[CODE]] في سطر لحاله، وتحت كل وحدة سطر واحد ليش تناسبه: "
                      "من كلامه هو أو من شكلها الحقيقي (look). لا تكتب السعر ولا الوزن (البطاقة فيها). لا تقل آخر قطعة ولا "
                      "الكمية محدودة. لا تدّعي تعرف ذوقه. اختم بسؤال واحد: أي وحدة أقرب لك، ولا أطلع لك أخف أو أثقل؟"),
    "price_breakdown": ("اشرح بسطر من هذه الأرقام بالضبط: سعر جرام 21 اليوم × الوزن + المصنعية = الإجمالي. أي عملة ثانية من هذا "
                        "الحساب فقط. إذا قال غالي اعرض قطعة أخف بنفس الروح. لا خصم من عندك."),
    "piece_details": ("صف القطعة من بياناتها ووصف شكلها فقط، بثلاث أسطر بالكثير. لا تخترع خدمة (تعديل مقاس، تفصيل، توصيل). "
                      "وإذا سأل عن شي مو مكتوب هنا، قل إنك ما عندك معلومة مؤكدة عنه."),
    "offer_purchase": ("ظهرت له أزرار الشراء تحت (صفحة القطعة وواتساب فريق المبيعات). اكتب سطر واحد يختم بالخطوة الجاية، "
                       "بدون ما تذكر العربون، وبدون تثبيت سعر ولا تقسيط ولا آجل."),
    "handoff_to_owner": "سطر واحد: فريق المبيعات يكمل معه على الواتساب (الزر تحت)، بدون وعود.",
}


# ---------------------------------------------------------------- the check before a reply goes out
_NUM = re.compile(r"(?<![a-z\d])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?:\s*(مليون|ملايين|الف|الاف|k)(?![a-zا-ي]))?")
_MULT = {"مليون": 1e6, "ملايين": 1e6, "الف": 1e3, "الاف": 1e3, "k": 1e3}
_UNITS = {"واحد": 1, "اثنين": 2, "ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6, "سته": 6,
          "سبع": 7, "سبعه": 7, "ثمان": 8, "ثمانيه": 8, "تسع": 9, "تسعه": 9, "عشر": 10, "عشره": 10}
_BIG = {"مليون": 1e6, "ملايين": 1e6, "الف": 1e3, "الاف": 1e3, "ميه": 100, "مئه": 100}
_DUAL = {"مليونين": 2e6, "الفين": 2e3, "ميتين": 200}


def numbers(text, with_precision=False, words=False):
    """Numbers in a text (Arabic or Western digits, 1,234 / 1.5 مليون / 300 ألف), each with how exact it is written.
    words=True also reads numbers written in words ("ثلاثة مليون", "مليونين"): used for what the customer said."""
    t = norm(text)
    t = re.sub(r"\[\[[^\]]*\]\]", " ", t)
    out = []
    for m in _NUM.finditer(t):
        ip, dec, unit = m.group(1).replace(",", ""), m.group(2), m.group(3)
        mult = _MULT.get(unit or "", 1)
        v = float(ip + ("." + dec if dec else "")) * mult
        if dec:
            prec = 10 ** (-len(dec)) * mult
        else:
            d, z = len(ip.lstrip("0") or "0"), len(ip) - len(ip.rstrip("0"))
            sig = max(d - z, min(2, d))
            prec = 10 ** max(0, d - sig) * mult
        out.append((v, prec) if with_precision else v)
    if words:      # "ثلاثة مليون", "مليونين", "مليون ونص" (never "ألف مبروك")
        for m in re.finditer(r"(?:(" + "|".join(_UNITS) + r")\s+)?(" + "|".join(list(_DUAL) + list(_BIG)) +
                             r")(?!\s*(مبروك|شكر|سلامه|مرحب|هلا|الحمد))(\s+و\s*نص|\s+ونص)?", t):
            u, big, half = m.group(1), m.group(2), m.group(4)
            base = _DUAL.get(big) or _BIG[big] * (_UNITS.get(u, 1))
            v = base + ((_BIG.get(big) or base / 2) / 2 if half else 0)
            out.append((v, 0.5) if with_precision else v)
    return out


def _supported(v, prec, sources):
    if v <= 3 or v in (21,):
        return True
    return any(abs(v - s) <= prec / 2 + 1e-6 for s in sources)


SCARCITY = _rx(["اخر قطعه", "اخر واحده", "اخر واحد", "ما بقى", "ما بقي", "مابقى", "ما باقي غير", "باقي وحده",
                "باقي واحد", "الكميه محدوده", "كميه محدوده", "القطعه الوحيده", "الوحيده المتوفره", "الوحيد المتوفر",
                "الوحيده اللي عندنا", "الوحيد اللي عندنا", "تخلص بسرعه", "بتخلص", "عليها طلب", "عليه طلب",
                "الحق عليها", "الحق عليه", "قبل لا تروح", "قبل ما تروح", "قبل لا تنباع", "قبل ما تنباع",
                "قبل ما تخلص", "قبل لا تخلص", "فرصه ما تتعوض"])
# a story about stock the system never told: "the rings we had ran out"
STOCK_STORY = _rx(["خلصت", "خلص", "نفدت", "نفذت", "انتهت الكميه", "خلصت الكميه", "كانت متوفره", "كانت متاحه", "كانت موجوده",
                   "انباعت كلها", "خلص المخزون", "نزلت وخلصت"])
TASTE = ["ذوقك", "اختيارك", "اخترت", "قلت قبل", "ذكرت انك", "واضح انك تحب", "واضح انك تميل", "شكلك تحب", "اعرف انك تحب"]
JARGON = ["حضور", "تكوين", "متناظر", "طابع", "اللغه البصريه", "تفاصيل غنيه",
          # how the system works is not the customer's business
          "برمز عرض", "رمز عرض", "معروضه برمز", "اللي رجع لي", "رجع لي البحث", "نتيجه البحث", "حسب البحث", "الاداه", "الادوات"]
BANNED = _rx(["صاله", "مغتربين", "مغترب", "زياره خاصه", "صاحب المحل"])
BRANCH = re.compile(r"(^|\s|ال|ب|و|ف|ل)(فرع|فروع)")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
NEG = {"ما", "لا", "مو", "مب", "مش", "بدون", "ولا", "ليس", "غير", "عدم", "ممنوع", "مافيه", "مافي", "ماعندنا",
       "مانقدر", "ماقدر", "مااقدر", "مانسوي", "مانشتغل", "مايمدي", "ماهو", "مانعطي", "مانثبت", "مايثبت", "يوجد"}
PROMISES = {
    "price_lock": re.compile(_EDGE + r"(?:و|ف)?(نثبت|اثبت|ثبت|تثبيت|يثبت|نثبتلك|اثبتلك|نثبتها|اثبتها|ثبتنا)(\s+لك)?\s+(ال)?سعر|السعر\s+ثابت\s+لين"),
    "deposit": re.compile(_EDGE + r"(?:و|ف|ب)?(?:ال)?(عربون|نحجز\w*|احجز\w*|تحجز\w*|حجز\w*)" + _END),
    "instalments": re.compile(_EDGE + r"(?:و|ب)?(?:ال)?(تقسيط|اقساط|قسط|دفعات|تقسطها|نقسط\w*)" + _END),
    "pay_later": re.compile(r"(تدفع|ادفع|الدفع|يدفع)\s+(الباقي\s+)?(بعدين|لاحقا|بعد\s+(اسبوع|شهر|الراتب))|بالاجل|" + _EDGE + r"اجل" + _END),
    "trade_in": re.compile(r"(نبدل|نبادل|تبدل|نستبدل|استبدال|تبديل)\s+(لك\s+)?(ذهب|الذهب|ذهبك|القطعه|قطعتك)"),
    "repair": re.compile(_EDGE + r"(?:و)?(نصلح\w*|تصليح|صيانه|نلحم\w*|تلحيم)" + _END),
    "delivery": re.compile(_EDGE + r"(?:و)?(نوصل\w*|توصيل|نشحن\w*|شحن)" + _END),
    "custom": re.compile(_EDGE + r"(نفصل\w*|تفصيل|مقاس خاص|نعدل المقاس|تعديل المقاس|نكبر\w*|نصغر\w*)" + _END),
    "discount": re.compile(_EDGE + r"(?:و|ب)?(?:ال)?(خصم|تخفيض|ننزل لك|انزل لك|نراعيك|اراعيك)" + _END),
    "return": re.compile(_EDGE + r"(?:و)?(ترجعها|ترجعه|نرجع لك|نسترجع|استرجاع|ترجع لك الفلوس)" + _END),
}
KARAT_OTHER = re.compile(r"عيار\s*(18|22|24)|(18|22|24)\s*(قيراط|عيار)|ذهب\s*(18|22|24)")
SEVERE = {"number", "scarcity", "promise", "karat", "banned", "branch", "entity", "taste", "relative", "stock_story"}


def _negated(t, start):
    """«ما نثبت السعر»، «لا تقسيط»، «بدون عربون»، «مانحجز»: an explanation that says no, not a promise."""
    before = [w[1:] if w[:1] in "وف" and w[1:] in NEG else w for w in t[:start].split()[-4:]]      # «فما»، «وما»
    return any(w in NEG or (w.startswith("ما") and len(w) >= 5 and w[2] in "نيتا") for w in before)


def _kind_of(kind_text):
    k = norm(kind_text or "")
    if "طقم" in k:
        return "طقم"
    if "سلسل" in k or "تعليق" in k:
        return "سلسلة"
    return k


def check_reply(text, env):
    """Checks a model reply before it reaches the customer.
    env: sources (numbers the system or the customer gave), customer (all the customer's words, normalised),
    kinds {code: piece type}, no_cards, max_cards, deposit_ok, custom_ok, found_one, prev (previous reply),
    stated_taste, found (codes the search returned), asking (the customer asked for pieces), discovery.
    -> {"text": the reply after the automatic fixes, "problems": [(key, note)], "severe": bool}"""
    fixed = EMOJI.sub("", text or "")
    fixed = re.sub(r"[ \t]{2,}", " ", fixed)
    codes = list(dict.fromkeys(c.upper() for c in re.findall(r"\[\[([A-Za-z0-9]+)\]\]", fixed)))
    if env.get("no_cards") and codes:
        fixed = re.sub(r"\s*\[\[[A-Za-z0-9]+\]\]\s*", "\n", fixed).strip()
        codes = []
    cap = int(env.get("max_cards") or 3)
    if len(codes) > cap:                                  # never more than three pieces in one reply
        for c in codes[cap:]:
            fixed = re.sub(r"\n?[^\n]*\[\[" + c + r"\]\][^\n]*(\n[^\n\[]*)?", "", fixed, flags=re.I)
        codes = codes[:cap]
    t = norm(fixed)
    plain = re.sub(r"\[\[[^\]]*\]\]", " ", t)
    probs = []
    # 1) every number from the system or from the customer
    src = env.get("sources") or []
    bad = [m.group(0).strip() for m, (v, p) in zip(_NUM.finditer(plain), numbers(plain, True)) if not _supported(v, p, src)]
    if bad:
        probs.append(("number", "في ردك رقم مو من النظام ولا من كلام الزبون (" + "، ".join(bad[:4]) +
                      "). لا تكتب أي رقم إلا من نتيجة أداة أو من معلومات المحل أو من كلامه هو. وإذا ما عندك الرقم لا تكتبه."))
    # 2) no invented scarcity or hurry
    m = SCARCITY.search(" " + plain + " ")
    if m and not (env.get("found_one") and "الوحيد" in m.group(0)):
        probs.append(("scarcity", "لا تقل آخر قطعة ولا الكمية محدودة ولا أي استعجال: النظام ما قال كذا."))
    if not env.get("sold_ok"):
        st_ = STOCK_STORY.search(" " + plain + " ")
        if st_ and not _negated(" " + plain + " ", st_.start()):
            probs.append(("stock_story", "لا تقول إن شي كان متوفر وخلص أو انباع: النظام ما قال كذا. قل بس «ما عندنا الحين»."))
    # 3) taste the customer never stated, internal words
    said = env.get("customer") or ""
    taste = [w for w in TASTE if w in plain and w not in said]
    if env.get("stated_taste"):
        taste = [w for w in taste if w != "ذوقك"]
    if taste:
        probs.append(("taste", "لا تدّعي إنك تعرف ذوقه ولا تنسب له كلام ما قاله (" + "، ".join(taste) +
                      "). إذا سأل كيف عرفت، قل بصراحة إنك كنت تقترح."))
    jar = [w for w in JARGON if w in plain and w not in said]
    if jar:
        probs.append(("jargon", "كلمات داخلية (" + "، ".join(jar) + "): الزبون ما يهمه كيف يشتغل النظام. قل كلام بيّاع "
                                "(شغل ناعم، مليان، ثقيل، خفيف، طويل)، وقل «عندنا» أو «ما عندنا الحين» بدل كلام البحث والرموز."))
    # 4) words the shop never uses
    b = BANNED.search(" " + plain + " ")
    if b:
        probs.append(("banned", f"كلمة ممنوعة في ردك: «{b.group(0).strip()}». قل المحل أو فريق المبيعات."))
    if RELATIVES.search(" " + plain + " "):
        probs.append(("relative", "لا تذكر نساء الزبون بالقرابة أبداً. قل العروس أو صاحبة المناسبة فقط."))
    if BRANCH.search(plain):
        probs.append(("branch", "لا تذكر فرع ولا فروع. المحل في كلامك واحد: جمال المشرقي للذهب والمجوهرات، بجوار البوابة "
                                "الرئيسية لمركز جرعان في إب."))
    # 5) promises the shop does not make (an explanation that says "no" is fine)
    allowed = {"deposit"} if env.get("deposit_ok") else set()
    if env.get("custom_ok"):
        allowed.add("custom")
    hit = []
    for name, rx in PROMISES.items():
        if name in allowed:
            continue
        for mm in rx.finditer(" " + plain + " "):
            if not _negated(" " + plain + " ", mm.start()):
                hit.append(name)
                break
    if hit:
        names = {"price_lock": "تثبيت السعر", "deposit": "الحجز أو العربون", "instalments": "التقسيط", "pay_later": "الدفع لاحقاً",
                 "trade_in": "تبديل الذهب", "repair": "التصليح", "delivery": "التوصيل", "custom": "التفصيل أو تعديل المقاس",
                 "discount": "الخصم", "return": "الإرجاع"}
        probs.append(("promise", "ردك فيه شي المحل ما يسويه (" + "، ".join(names[h] for h in hit) + "). البيع بسعر الذهب ساعة "
                                 "الشراء يد بيد: لا تثبيت سعر ولا تقسيط ولا آجل ولا تبديل ولا تصليح ولا توصيل ولا خصم من عندك، "
                                 "ولا تعرض الحجز من نفسك. إذا يحتاج شي من هذا، فريق المبيعات يرد عليه."))
    for mm in KARAT_OTHER.finditer(plain):
        if not _negated(plain, mm.start()):
            probs.append(("karat", "ذهبنا كله عيار 21 ومعه جنيهات ذهب. لا تقل إن عندنا عيار ثاني."))
            break
    # 6) a piece called by another kind (a chain is never a set)
    kinds = env.get("kinds") or {}
    marks = list(re.finditer(r"\[\[([A-Za-z0-9]+)\]\]", fixed))
    for i, mk in enumerate(marks):
        code = mk.group(1).upper()
        real = _kind_of(kinds.get(code))
        if not real:
            continue
        own = norm(fixed[mk.end(): marks[i + 1].start() if i + 1 < len(marks) else len(fixed)].split("\n\n")[0])
        intro = norm(fixed[:marks[0].start()])
        said_set = re.search(r"(^|\s)(ال|و|ب)?(طقم|اطقم)", own)
        said_chain = re.search(r"(^|\s)(ال|و|ب)?(سلسله|سلاسل)", own)
        set_intro = len(marks) == 1 and re.search(r"(^|\s)(ال|و|ب)?(طقم|اطقم)", intro) and not re.search("عقد|سلسل|حلق|خاتم|اسور|حزام", intro)
        if (said_set or set_intro) and real != "طقم":
            probs.append(("entity", f"سميت القطعة [[{code}]] طقم وهي {kinds.get(code)}. سمّها باسم نوعها الصحيح."))
            break
        if said_chain and real == "طقم":
            probs.append(("entity", f"سميت القطعة [[{code}]] سلسلة وهي طقم كامل. سمّها طقم."))
            break
    # 7) the same reply again, more than one question
    prev = norm(re.sub(r"\[\[[^\]]*\]\]", " ", env.get("prev") or ""))
    if prev and len(plain) > 30 and difflib.SequenceMatcher(None, plain.strip(), prev.strip()).ratio() > 0.85:
        probs.append(("repeat", "ردك نفس ردك السابق تقريباً. غيّر الصياغة وقل شي جديد يفيده."))
    if question_count(plain) > 1:
        probs.append(("questions", "في ردك أكثر من سؤال. خله سؤال واحد بس."))
    # 8) pieces the search found but the reply hid
    found = list(dict.fromkeys(env.get("found") or []))
    if found and env.get("asking") and not codes and not env.get("no_cards") and not env.get("discovery"):
        probs.append(("hidden", "البحث رجّع قطع متوفرة (" + "، ".join(f"[[{c}]]" for c in found[:3]) + ") وأنت ما عرضت شي. "
                                "اعرضها بكتابة رمزها في سطر مستقل، وإذا ما تطابق طلبه تماماً قل الفرق بجملة صادقة."))
    return {"text": fixed.strip(), "problems": probs, "severe": any(k in SEVERE for k, _ in probs), "codes": codes}


def question_count(text):
    """Questions in a reply; «أي وحدة أقرب لك؟ ولا أطلع لك أخف؟» is one question with its alternative."""
    t = re.sub(r"[؟?](?=\s*(و?لا|او|أو)\s)", "،", text or "")
    return t.count("؟") + t.count("?")


def rewrite_note(problems, draft=""):
    head = ("هذي مسودة ردك على رسالة الزبون الأخيرة (ما وصلته):\n«" + draft.strip() + "»\n\n") if draft else ""
    return (head + "اكتب الرد للزبون من جديد كاملاً، بنفس الأسلوب القصير، مع هذا التصحيح:\n" +
            "\n".join("- " + n for _, n in problems))


SAFE_SHOW = "هذي أقرب القطع لطلبك، والسعر في البطاقة شامل المصنعية بسعر اليوم.\nأي وحدة أقرب لك؟"
SAFE_HANDOFF = "هذي ما عندي فيها معلومة مؤكدة. خلني أوصلك بفريق المبيعات على الواتساب يتأكدون لك مباشرة."
MISUNDERSTOOD_LINE = "يبدو إني ما فهمت عليك زين، وفريق المبيعات يقدر يكمل معك على الواتساب مباشرة (الزر تحت)."
REPEAT_LINE = "خلني أوصلك بفريق المبيعات على الواتساب يجاوبونك مباشرة (الزر تحت)."
LONG_LINE = "وإذا تحب يكمل معك فريق المبيعات على الواتساب، الزر تحت."
BUSY = "المساعد مزحوم الحين. تقدر تتصفح القطع في الموقع، أو يكمل معك فريق المبيعات على الواتساب (الزر تحت)."
OFF = "تقدر تتصفح القطع في الموقع، أو يكمل معك فريق المبيعات على الواتساب (الزر تحت)."

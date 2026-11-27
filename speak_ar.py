"""Spoken Arabic for the voice: numbers said in words, the written reply cleaned for a voice to read."""
import re

_ONES = ["صفر", "واحد", "اثنين", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة", "أحد عشر", "اثنا عشر",
         "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
_TENS = ["", "", "عشرين", "ثلاثين", "أربعين", "خمسين", "ستين", "سبعين", "ثمانين", "تسعين"]
_HUND = ["", "مية", "ميتين", "ثلاثمية", "أربعمية", "خمسمية", "ستمية", "سبعمية", "ثمانمية", "تسعمية"]
_BIG = [(10 ** 9, "مليار", "مليارين", "مليارات"), (10 ** 6, "مليون", "مليونين", "ملايين"), (1000, "ألف", "ألفين", "آلاف")]


def _small(n):
    """0 < n < 1000 in words, the way it is said."""
    h, r = divmod(n, 100)
    out = [_HUND[h]] if h else []
    if r:
        out.append(_ONES[r] if r < 20 else (_TENS[r // 10] if r % 10 == 0 else _ONES[r % 10] + " و" + _TENS[r // 10]))
    return " و".join(out)


def num_words(n):
    """A whole number in spoken Arabic: 2350000 -> «مليونين وثلاثمية وخمسين ألف»."""
    n = int(n)
    if n == 0:
        return _ONES[0]
    out = []
    for size, one, two, many in _BIG:
        k, n = divmod(n, size)
        if k:
            out.append(one if k == 1 else two if k == 2 else (_ONES[k] + " " + many) if k <= 10 else num_words(k) + " " + one)
    if n:
        out.append(_small(n))
    return " و".join(out)


def _frac(whole, frac):
    w = num_words(whole) if whole else ""
    f = {"5": "نص", "50": "نص", "25": "ربع", "75": "ثلاث أرباع"}.get(frac.rstrip("0") or "0") if frac.rstrip("0") in ("5", "25", "75") else None
    if f:
        return (w + " و" + f) if w else f
    frac = frac.rstrip("0")
    if not frac:
        return w or _ONES[0]
    return (w or _ONES[0]) + " فاصلة " + num_words(int(frac))


def _number(m):
    s = m.group(0)
    raw = s.replace(",", "").replace("٬", "")
    if re.fullmatch(r"\+?\d{9,}", raw):                     # a phone number: digit by digit
        return " ".join(_ONES[int(d)] for d in raw if d.isdigit())
    if "." in raw:
        a, b = raw.split(".", 1)
        return _frac(int(a or 0), b)
    return num_words(int(raw))


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


SAY_AS = [(r"(?<![\u0600-\u06FF])للبس(?![\u0600-\u06FF])", "للزينة"), (r"(?<![\u0600-\u06FF])اللبس(?![\u0600-\u06FF])", "الزينة"),
          (r"المشرقي", "المَشْرِقي"), (r"جرعان", "جَرْعان")]


def speakable(text, max_chars=320):
    """What the voice says for a written reply: no codes, links, symbols or emoji, numbers in words, short."""
    t = (text or "").translate(_AR_DIGITS).replace("ـ", "")
    t = re.sub(r"\s*[—–]\s*", "، ", t)
    t = re.sub(r"\[\[[A-Za-z0-9]+\]\]", "", t)
    t = t.replace("الزر تحت", "الزر على الشاشة").replace("تحت المحادثة", "على الشاشة")
    t = re.sub(r"\((?:بتاريخ|آخر تحديث|تحديث)[^)]*\)", "", t)
    t = re.sub(r"،?\s*(?:حسب|على)\s+آخر\s+سعر\s+مسج[ّ]?ل[^،.\n]*", "", t)          # «حسب آخر سعر مسجّل بتاريخ ... مساءً»
    t = re.sub(r"،?\s*بتاريخ\s+[\d/\-]+[^،.\n]*?(?:مساءً|مساء|صباحاً|صباحا|م|ص)?(?=[،.\n]|$)", "", t)
    t = re.sub(r"https?://\S+|www\.\S+", "", t)
    t = re.sub(r"(?m)^\s*(?:[-•*·▪●◦]|\d+[.)])\s+", "", t)                 # list marks at the start of a line
    t = re.sub(r"\s*\(\s*", "، ", t).replace(")", "")
    t = re.sub(r"(\d)\s*K\b", r"\1", t)
    t = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", r"\1 بالمية", t)
    t = re.sub(r"(\d)\s*(?:جم|غ|g|gm)\b", r"\1 جرام", t)
    t = re.sub(r"(?<!\w)(?:ر\.ي|YER|ريال يمني)(?!\w)", "ريال", t)
    t = re.sub(r"(\d{1,2}):(\d{2})", lambda m: m.group(1) + (" و" + str(int(m.group(2))) if int(m.group(2)) else ""), t)
    t = t.replace("×", " ضرب ").replace("+", " زائد ").replace("=", " يساوي ").replace("$", " دولار ")
    t = re.sub(r"\+?\d[\d,٬]*(?:\.\d+)?", _number, t)
    t = re.sub(r"[^؀-ۿ\s.,،؛;:!?؟\-]", " ", t)                  # emoji, symbols, Latin letters
    t = re.sub(r"[ \t]*\n+[ \t]*", ". ", t.strip())
    t = re.sub(r"\s*([.,،؛:!?؟])(\s*[.,،؛:!?؟])+", r"\1", t)
    t = re.sub(r"\s+([.,،؛:!?؟])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -:،,")
    t = re.sub(r"^[.،,]\s*", "", t)
    if len(t) > max_chars:                                                 # long written answers: the first sentences
        cut = t[:max_chars]
        stop = max(cut.rfind(x) for x in (".", "؟", "!", "؛"))
        if stop < max_chars * 0.45:
            stop = cut.rfind("،")
        t = (cut[:stop + 1] if stop > 40 else cut.rsplit(" ", 1)[0]).rstrip("،, ") + " والباقي مكتوب لك على الشاشة."
    for a, b in SAY_AS:
        t = re.sub(a, b, t)
    return t

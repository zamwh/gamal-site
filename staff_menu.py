# -*- coding: utf-8 -*-
"""Report buttons for the shop's staff in the Telegram bot (a keyboard that stays under the chat).
Every number comes straight from the database through the same read-only tools the internal agent uses:
no AI, so the reports are instant, free and exact. Free questions still go to the internal agent."""
import datetime as dt
import json
from collections import Counter

import ops

# the keyboard under the chat: one button per section; each opens its own options inside the chat
SECTIONS = [["📊 التقارير", "🔔 التنبيهات"], ["💎 القطع والصور", "📢 قناة المحل"], ["❤️ اهتمامات العملاء", "👥 المسؤولين"], ["⚙️ التحكم"]]
# section -> options (label, callback). Pressing an option rewrites the section's message in place.
OPTIONS = {
    "التقارير": [("📅 مبيعات اليوم", "r:today"), ("⏮️ مبيعات أمس", "r:yday"), ("🗓️ آخر 7 أيام", "r:week"), ("📆 هذا الشهر", "r:month"),
                 ("📦 المخزون الحالي", "r:stock"), ("🧾 آخر الفواتير", "r:inv"), ("🌐 زوار الموقع اليوم", "r:web"),
                 ("💰 سعر الذهب اليوم", "r:price"), ("🧪 جودة الوكيل", "r:qa")],
    "التنبيهات": [("🔔 آخر التنبيهات", "n:list"), ("🛒 تنبيه الشراء", "r:restock"), ("📌 الحجوزات المفتوحة", "r:res")],
    "القطع والصور": [("📷 قطع بدون صور", "p:none"), ("✨ ناقصها مخمل أو قريبة", "p:part"), ("🆕 آخر القطع المضافة", "p:latest")],
    "اهتمامات العملاء": [("❤️ طلبوا مثلها", "i:want"), ("👍 تفاعل القناة", "i:react"), ("👀 مشاهدات الموقع", "r:int"),
                          ("🏷️ الاهتمام حسب النوع", "i:kind"), ("🔎 طلبات ما توفرت", "r:dem"),
                          ("🔍 بحثوا وما لقوا", "i:unmet")],
    "المسؤولين": [("➕ إضافة مسؤول", "o:add"), ("📋 المسؤولين الحاليين", "o:list")],
}
INTRO = {"التقارير": "📊 التقارير: اختر من تحت، ويطلع التقرير هنا.",
         "التنبيهات": "🔔 التنبيهات: يوصلك هنا كل بيع وكل حجز وتنبيه الشراء.",
         "القطع والصور": "💎 القطع والصور: اختر من تحت.",
         "اهتمامات العملاء": "❤️ اهتمامات العملاء: وش يعجب الزبائن ووش يطلبونه، عشان تقرر وش تنزّل من بضاعة.",
         "المسؤولين": "👥 المسؤولين: كل مسؤول يوصله البيع والتنبيهات وصور القطع والتقارير والوكيل الداخلي. "
                      "تضيف مسؤول برابط دعوة يشتغل مرة وحدة."}
SECTION_OF = {cb: name for name, opts in OPTIONS.items() for _, cb in opts}
REPORT_CB = {"r:today": "مبيعات اليوم", "r:yday": "مبيعات أمس", "r:week": "مبيعات آخر 7 أيام", "r:month": "مبيعات هذا الشهر",
             "r:stock": "المخزون الحالي", "r:inv": "آخر الفواتير", "r:int": "الأكثر اهتماماً", "r:web": "زوار الموقع اليوم",
             "r:dem": "طلبات ما توفرت", "r:price": "سعر الذهب اليوم", "r:restock": "تنبيه الشراء", "r:res": "الحجوزات"}
BUTTONS = set(REPORT_CB.values())       # typing a report's name still works
VERSION = 5          # bump when the buttons change: linked staff get the new keyboard once


def section_name(text):
    """A section button's text, with or without its emoji (older keyboards had none)."""
    t = (text or "").strip()
    for name in list(OPTIONS) + ["قناة المحل", "التحكم"]:
        if t == name or t.endswith(" " + name):
            return name
    return None


DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
RES_AR = {"pending": "بانتظار التأكيد", "active": "مؤكد", "done": "تم", "completed": "تم", "expired": "انتهى",
          "cancelled": "ملغي", "rejected": "مرفوض"}


def keyboard():
    return {"keyboard": [[{"text": t} for t in row] for row in SECTIONS], "resize_keyboard": True, "is_persistent": True,
            "input_field_placeholder": "اختر قسم، أو اسأل الوكيل أي سؤال"}


def section_kb(name, muted=None):
    """Inline options of a section, two a row."""
    opts = list(OPTIONS.get(name, []))
    if name == "التنبيهات" and muted is not None:
        opts.append(("🔊 شغّل التنبيهات عندي", "n:on") if muted else ("🔕 وقّف التنبيهات عندي", "n:off"))
    rows = [opts[i:i + 2] for i in range(0, len(opts), 2)]
    return {"inline_keyboard": [[{"text": t, "callback_data": cb} for t, cb in row] for row in rows]}


def _piece_line(p):
    return f"{p['title'] or p['type']} {p['code']}"


def wanted(app):
    rows = app.store.q("""SELECT p.code, p.title, p.type, p.weight, p.status, COUNT(*) n FROM channel_likes l JOIN pieces p ON p.code=l.code
                          GROUP BY p.code ORDER BY n DESC, MAX(l.ts) DESC LIMIT 12""")
    if not rows:
        return "❤️ طلبوا مثلها\nما أحد طلب للحين. الزر يطلع تحت كل قطعة تنباع في القناة."
    return "\n".join(["❤️ طلبوا مثلها (من زر «أبغى مثلها» في القناة)"] +
                     [f"{_piece_line(r)} · {_g(r['weight'])} جم: {r['n']} طلب" for r in rows])


def reactions(app):
    rows = app.store.q("""SELECT p.code, p.title, p.type, p.status, c.reactions n FROM channel_posts c JOIN pieces p ON p.code=c.code
                          WHERE c.reactions>0 ORDER BY c.reactions DESC LIMIT 12""")
    if not rows:
        return "👍 تفاعل القناة\nما فيه تفاعل للحين. يوصل البوت عدد التفاعلات بعد دقائق من حدوثها."
    st = {"sold": " (انباعت)", "available": "", "reserved": " (محجوزة)"}
    return "\n".join(["👍 تفاعل القناة على كل قطعة"] + [f"{_piece_line(r)}{st.get(r['status'], '')}: {r['n']} تفاعل" for r in rows])


def by_kind(app):
    """Interest per kind of piece, so the owner sees which kinds to stock more of."""
    s = app.store
    kinds = {}
    def k(t):
        return kinds.setdefault(t or "غير محدد", {"want": 0, "react": 0, "views": 0, "saves": 0, "sold": 0})
    for r in s.q("SELECT p.type, COUNT(*) n FROM channel_likes l JOIN pieces p ON p.code=l.code GROUP BY p.type"):
        k(r["type"])["want"] += r["n"]
    for r in s.q("SELECT p.type, SUM(c.reactions) n FROM channel_posts c JOIN pieces p ON p.code=c.code GROUP BY p.type"):
        k(r["type"])["react"] += r["n"] or 0
    for r in s.q("""SELECT p.type, COUNT(*) n FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id JOIN pieces p ON p.id=ii.piece_id
                    WHERE i.kind='sale' AND i.status='ok' AND i.created_at>=? GROUP BY p.type""",
                 ((dt.date.today() - dt.timedelta(days=90)).isoformat(),)):
        k(r["type"])["sold"] += r["n"]
    pi = app.analytics.piece_interest() if getattr(app, "analytics", None) else {}
    if pi:
        types = {r["code"]: r["type"] for r in s.q("SELECT code, type FROM pieces")}
        for code, (v, sv) in pi.items():
            if code in types:
                x = k(types[code]); x["views"] += v; x["saves"] += sv
    rows = sorted(kinds.items(), key=lambda kv: (kv[1]["want"] * 5 + kv[1]["saves"] * 3 + kv[1]["react"] + kv[1]["views"] * 0.2 + kv[1]["sold"] * 2), reverse=True)
    rows = [(t, x) for t, x in rows if any(x.values())]
    if not rows:
        return "🏷️ الاهتمام حسب النوع\nما فيه بيانات للحين."
    out = ["🏷️ الاهتمام حسب النوع (الأعلى أول)"]
    for t, x in rows[:10]:
        parts = [f"{x['want']} طلبوا مثلها" if x["want"] else "", f"{x['react']} تفاعل" if x["react"] else "",
                 f"{x['views']} شافوها" if x["views"] else "", f"{x['saves']} حفظوها" if x["saves"] else "",
                 f"انباع {x['sold']} في 3 شهور" if x["sold"] else ""]
        out.append(f"{t}: " + " · ".join(p for p in parts if p))
    return "\n".join(out)


def render(app, key):
    """Any option or report name -> its text (caller holds the lock)."""
    fn = {"n:list": notifications, "p:latest": latest_pieces, "i:want": wanted, "i:react": reactions, "i:kind": by_kind,
          "r:qa": quality, "i:unmet": unmet}.get(key)
    return fn(app) if fn else report(app, REPORT_CB.get(key, key))


def notifications(app):
    rows = ops.notifications(app.store, 10)["items"]
    if not rows:
        return "آخر التنبيهات\nما فيه تنبيهات."
    return "\n".join(["آخر التنبيهات"] + [f"{_when(r['ts'])} · {r['title']}" for r in rows])


def latest_pieces(app):
    import core
    rows = app.store.q("""SELECT p.*, b.name branch FROM pieces p JOIN branches b ON b.id=p.branch_id
                          ORDER BY p.created_at DESC, p.rowid DESC LIMIT 8""")
    if not rows:
        return "آخر القطع المضافة\nما فيه قطع."
    ST = {"available": "متاحة", "reserved": "محجوزة", "sold": "مباعة", "inactive": "موقوفة"}
    out = ["آخر القطع المضافة"]
    for p in rows:
        r = core.piece_roles(p)
        n = sum(1 for k in core.PHOTO_ROLES if r.get(k))
        out.append(f"{p['code']} · {p['title'] or p['type']} · {_g(p['weight'])} جم · {p['branch']} · {ST.get(p['status'], p['status'])}"
                   f" · {'بدون صور' if not n else 'الصور كاملة' if n == 3 else f'{n} من 3 صور'}"
                   + ("" if p["show_online"] else " · مخفية من الموقع"))
    return "\n".join(out)


def _n(x):
    return f"{float(x or 0):,.0f}"


def _g(x):
    return f"{float(x or 0):,.2f}".rstrip("0").rstrip(".")


def _inv(n):
    n = int(n or 0)
    return "فاتورة وحدة" if n == 1 else "فاتورتين" if n == 2 else f"{n} فواتير" if n <= 10 else f"{n} فاتورة"


def _pcs(n):
    n = int(n or 0)
    return "قطعة وحدة" if n == 1 else "قطعتين" if n == 2 else f"{n} قطع" if n <= 10 else f"{n} قطعة"


def _by_branch(app, rows):
    order = [b["name"] for b in app.store.branches()]
    return sorted(rows or [], key=lambda x: order.index(x["branch"]) if x["branch"] in order else 99)


def _day(d):
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return f"{DAYS[d.weekday()]} {d.day}/{d.month}"


def _when(ts):
    try:
        t = dt.datetime.fromisoformat(str(ts)[:19])
        return f"{t.day}/{t.month} {t:%H:%M}"
    except Exception:
        return str(ts or "")[:16]


def sales(app, a, b, title):
    t = app.staff.tool
    r = t("sales_summary", {"date_from": a, "date_to": b})
    if not r.get("invoices"):
        return f"{title}\nما فيه مبيعات."
    out = [title, f"الإجمالي: {_n(r['total'])} ريال",
           f"{_inv(r['invoices'])} · الذهب المباع {_g(r['grams'])} جرام"]
    if float(r.get("making_discount") or 0):
        out.append(f"خصم المصنعية: {_n(r['making_discount'])} ريال")
    if r.get("by_branch"):
        out += ["", "حسب الفرع:"] + [f"{x['branch']}: {_n(x['total'])} ريال · {_inv(x['invoices'])}" for x in _by_branch(app, r["by_branch"])]
    if a != b and 1 < len(r.get("by_day") or []) <= 7:
        out += ["", "حسب اليوم:"] + [f"{_day(x['day'])}: {_n(x['total'])} ريال · {_inv(x['invoices'])}" for x in r["by_day"]]
    top = t("top_sold", {"date_from": a, "date_to": b, "limit": 5}).get("items") or []
    if top:
        out += ["", "أعلى القطع:"] + [f"{x['description']}{' ' + x['code'] if x.get('code') else ''} · {_g(x['weight'])} جم · {_n(x['line_total'])}"
                                      for x in top]
    gb = r.get("gold_bought_from_customers") or {}
    if gb.get("n"):
        out += ["", f"شراء ذهب من الزبائن: {gb['n']} سند · {_n(gb['total'])} ريال"]
    return "\n".join(out)


def stock(app):
    r = app.staff.tool("stock_summary", {})
    ta = r.get("total_available") or {}
    if not ta.get("n"):
        return "المخزون الحالي\nما فيه قطع متاحة."
    out = ["المخزون الحالي", f"المتاح: {_pcs(ta['n'])} · {_g(ta['g'])} جرام",
           f"المحجوز: {r.get('reserved', 0)} · المعروض في الموقع: {r.get('online', 0)}"]
    out += ["", "حسب النوع:"] + [f"{x['kind']}: {_pcs(x['pieces'])} · {_g(x['grams'])} جم" for x in r.get("by_kind") or []]
    out += ["", "حسب الفرع:"] + [f"{x['branch']}: {_pcs(x['pieces'])} · {_g(x['grams'])} جم" for x in _by_branch(app, r.get("by_branch"))]
    return "\n".join(out)


def last_invoices(app):
    rows = app.store.q("""SELECT i.number, i.total, i.created_at, b.name branch FROM invoices i JOIN branches b ON b.id=i.branch_id
                          WHERE i.kind='sale' AND i.status='ok' ORDER BY i.created_at DESC, i.rowid DESC LIMIT 8""")
    if not rows:
        return "آخر الفواتير\nما فيه فواتير."
    return "\n".join(["آخر الفواتير"] + [f"{r['number']} · {_n(r['total'])} ريال · {r['branch']} · {_when(r['created_at'])}" for r in rows])


def reservations(app):
    r = app.staff.tool("reservations", {"status": "all"})
    rows = [x for x in r.get("rows") or [] if x.get("status") in ("pending", "active")][:10]
    if not rows:
        return "الحجوزات\nما فيه حجوزات مفتوحة."
    return "\n".join(["الحجوزات المفتوحة"] + [f"{x['number']} · {x['piece']} {x['code']} · {RES_AR.get(x['status'], x['status'])}"
                                              + (f" · عربون {_n(x['deposit'])}" if float(x.get('deposit') or 0) else "")
                                              for x in rows])


def demand(app):
    r = app.staff.tool("demand", {})
    cats = r.get("open_by_category") or []
    if not cats:
        return "طلبات ما توفرت\nما فيه طلبات مفتوحة."
    out = ["طلبات الزبائن اللي ما توفرت (من المستشار في الموقع)"]
    out += [f"{x['category'] or 'غير محدد'}: {x['n']} طلب" + (f" · متوسط الميزانية {_n(x['avg_budget'])}" if x.get("avg_budget") else "")
            for x in cats]
    latest = r.get("latest") or []
    if latest:
        out += ["", "آخر الطلبات:"] + [f"{_when(x['ts'])} · {x['description'] or x['category'] or ''}"[:120] for x in latest[:5]]
    return "\n".join(out)


def interest(app):
    rows = [x for x in app.staff.tool("piece_interest", {"limit": 8}).get("pieces") or [] if x["opened_by"] or x["saved_by"]]
    if not rows:
        return "👀 مشاهدات الموقع\nما فيه مشاهدات للحين."
    return "\n".join(["👀 مشاهدات الموقع (من يوم نزلت القطعة)"] +
                     [f"{x['name']} {x['code']}: شافها {x['opened_by']} · حفظها {x['saved_by']}" for x in rows])


def website(app):
    today = dt.date.today().isoformat()
    r = app.staff.tool("website_and_ai", {"date_from": today, "date_to": today})
    w = r.get("website") or {}
    out = ["الموقع اليوم", f"الزوار: {w.get('visitors') or 0} · الجلسات: {w.get('sessions') or 0}",
           f"مشاهدات القطع: {w.get('piece_views') or 0} · حفظوا قطع: {w.get('shortlist') or 0}",
           f"كلّموا المستشار: {w.get('ai_chat') or 0} · ضغطوا واتساب: {w.get('whatsapp') or 0}",
           f"طلبات شراء أو حجز: {w.get('requests') or 0}"]
    if "ai_cost_usd" in r:
        out.append(f"تكلفة الذكاء الاصطناعي اليوم: {r['ai_cost_usd']:.2f} دولار")
    return "\n".join(out)


def price(app):
    p = app.store.current_prices()
    if not p:
        return "سعر الذهب اليوم\nما فيه سعر معتمد. أدخله من البرنامج أو لوحة الإدارة."
    out = ["سعر الذهب (عيار 21)", f"بيع: {_n(p.get('k21_sell'))} · شراء: {_n(p.get('k21_buy'))} ريال للجرام"]
    if p.get("pound_sell"):
        out.append(f"الجنيه: بيع {_n(p.get('pound_sell'))} · شراء {_n(p.get('pound_buy'))}")
    out.append(f"آخر تحديث: {_when(p.get('created_at'))}")
    return "\n".join(out)


def restock(app):
    r = ops.restock_state(app.store)
    th = float(r.get("threshold_g") or 0)
    out = ["تنبيه الشراء", f"انباع {_g(r['sold_g'])} جرام من آخر شراء" + (f"، والحد {_g(th)} جرام." if th else ".")]
    if r.get("due"):
        out.append("وصلنا الحد: وقت الشراء. ولما تشتري، اضغط «اشتريت» في تنبيهات البرنامج عشان يبدأ العد من جديد.")
    return "\n".join(out)


def report(app, text):
    """The report for a button (caller holds the lock), or None when the text is not a report button."""
    today = dt.date.today()
    iso = lambda d: d.isoformat()
    if text == "مبيعات اليوم":
        return sales(app, iso(today), iso(today), f"مبيعات اليوم، {_day(today)}")
    if text == "مبيعات أمس":
        y = today - dt.timedelta(days=1)
        return sales(app, iso(y), iso(y), f"مبيعات أمس، {_day(y)}")
    if text == "مبيعات آخر 7 أيام":
        return sales(app, iso(today - dt.timedelta(days=6)), iso(today), "مبيعات آخر 7 أيام")
    if text == "مبيعات هذا الشهر":
        return sales(app, iso(today.replace(day=1)), iso(today), f"مبيعات هذا الشهر (من 1/{today.month})")
    fn = {"المخزون الحالي": stock, "آخر الفواتير": last_invoices, "الحجوزات": reservations, "طلبات ما توفرت": demand,
          "الأكثر اهتماماً": interest, "زوار الموقع اليوم": website, "سعر الذهب اليوم": price, "تنبيه الشراء": restock}.get(text)
    return fn(app) if fn else None


PROBLEM_AR = {"number": "رقم مو من النظام", "scarcity": "استعجال أو ندرة", "promise": "وعد المحل ما يسويه", "taste": "ادعاء معرفة الذوق",
              "jargon": "كلمات داخلية", "banned": "كلمة ممنوعة", "relative": "ذكر قرابة", "branch": "ذكر فروع",
              "karat": "عيار غير 21", "entity": "نوع قطعة غلط", "repeat": "تكرار نفس الرد", "questions": "أكثر من سؤال",
              "hidden": "ما عرض القطع اللي لقاها", "stock_story": "قصة مخزون مخترعة"}


def quality(app):
    """How the website assistant did in the last 7 days (test chats left out). From the logs, no AI."""
    s = app.store
    since = (dt.date.today() - dt.timedelta(days=6)).isoformat()
    rows = s.q("SELECT session, skills, cost FROM chat_logs WHERE role='assistant' AND ts>=? AND session NOT LIKE 'evaltest%'", (since,))
    if not rows:
        return "🧪 جودة الوكيل (آخر 7 أيام)\nما فيه محادثات."
    sessions = {r["session"] for r in rows}
    tpl = sum(1 for r in rows if (r["skills"] or "").startswith("tpl:"))
    plain = sum(1 for r in rows if (r["skills"] or "").startswith("plain:"))
    ai = len(rows) - tpl - plain
    tr = s.q("""SELECT tool, args FROM ai_trace WHERE ts>=? AND session NOT LIKE 'evaltest%'
                AND tool IN ('check', 'fallback')""", (since,))
    checks = [json.loads(r["args"] or "{}").get("problems") or [] for r in tr if r["tool"] == "check"]
    fallbacks = sum(1 for r in tr if r["tool"] == "fallback")
    serious = sum(1 for p in checks if set(p) & {"number", "scarcity", "promise", "karat", "taste", "entity"})
    why = Counter(k for p in checks for k in p)
    hand = s.q("SELECT reason FROM handoffs WHERE ts>=? AND session NOT LIKE 'evaltest%'", (since,))
    cost = sum(float(r["cost"] or 0) for r in rows)
    pct = lambda a, b: f"{round(100 * a / b)}%" if b else "0%"
    out = ["🧪 جودة الوكيل (آخر 7 أيام)",
           f"محادثات: {len(sessions)} · ردود: {len(rows)}",
           f"ردود جاهزة بدون ذكاء: {tpl} ({pct(tpl, len(rows))}) · ردود بالذكاء: {ai}" + (f" · بدون ذكاء (حد أو عطل): {plain}" if plain else ""),
           f"ردود انمسكت قبل ما توصل الزبون: {len(checks)} ({pct(len(checks), ai)} من ردود الذكاء)",
           f"منها أخطاء معلومات (رقم، وعد، ندرة، ذوق، نوع): {serious} ({pct(serious, ai)})",
           f"ردود آمنة بعد ما فشل التصحيح: {fallbacks}",
           f"تحويلات لفريق المبيعات: {len(hand)}"]
    if why:
        out.append("أكثر الأخطاء: " + "، ".join(f"{PROBLEM_AR.get(k, k)} {n}" for k, n in why.most_common(4)))
    if hand:
        out.append("أسباب التحويل: " + "، ".join(f"{k} {n}" for k, n in Counter(r["reason"] for r in hand).most_common(4)))
    out.append(f"التكلفة: {cost:.2f}$ · للمحادثة {cost / max(1, len(sessions)):.3f}$")
    return "\n".join(out)


def unmet(app):
    """What customers searched for and the shop did not have (last 30 days): a stocking signal."""
    s = app.store
    since = (dt.date.today() - dt.timedelta(days=29)).isoformat()
    try:
        rows = s.q("SELECT kind, budget, weight_max FROM unmet_searches WHERE ts>=? AND session NOT LIKE 'evaltest%'", (since,))
    except Exception:
        rows = []
    if not rows:
        return "🔍 بحثوا وما لقوا (آخر 30 يوم)\nما فيه بحث رجع فاضي."

    def band(r):
        bits = [r["kind"] or "أي نوع"]
        b = r["budget"]
        if b:
            bits.append(f"حدود {b / 1e6:.1f} مليون" if b >= 1e6 else f"حدود {int(b // 1000)} ألف")
        if r["weight_max"]:
            bits.append(f"أقل من {float(r['weight_max']):g} جم")
        return " · ".join(bits)
    cnt = Counter(band(r) for r in rows)
    return "🔍 بحثوا وما لقوا (آخر 30 يوم)\n" + "\n".join(f"{i}. {k}: {n} مرة" for i, (k, n) in enumerate(cnt.most_common(10), 1))

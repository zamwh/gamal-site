# -*- coding: utf-8 -*-
"""Report buttons for the shop's staff in the Telegram bot (a keyboard that stays under the chat).
Every number comes straight from the database through the same read-only tools the internal agent uses:
no AI, so the reports are instant, free and exact. Free questions still go to the internal agent."""
import datetime as dt

import ops

ROWS = [["مبيعات اليوم", "مبيعات أمس"],
        ["مبيعات آخر 7 أيام", "مبيعات هذا الشهر"],
        ["المخزون الحالي", "آخر الفواتير"],
        ["الحجوزات", "طلبات ما توفرت"],
        ["الأكثر اهتماماً", "زوار الموقع اليوم"],
        ["سعر الذهب اليوم", "تنبيه الشراء"],
        ["قطع بدون صور", "قناة المحل"]]
BUTTONS = {t for row in ROWS for t in row}
VERSION = 1          # bump when the buttons change: linked staff get the new keyboard once
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
RES_AR = {"pending": "بانتظار التأكيد", "active": "مؤكد", "done": "تم", "completed": "تم", "expired": "انتهى",
          "cancelled": "ملغي", "rejected": "مرفوض"}


def keyboard():
    return {"keyboard": [[{"text": t} for t in row] for row in ROWS], "resize_keyboard": True, "is_persistent": True,
            "input_field_placeholder": "اختر تقرير، أو اسأل الوكيل أي سؤال"}


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
        return "الأكثر اهتماماً\nما فيه مشاهدات للحين."
    return "\n".join(["الأكثر اهتماماً (من يوم نزلت القطعة)"] +
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

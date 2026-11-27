# -*- coding: utf-8 -*-
"""Full control of the system from Telegram (section «⚙️ التحكم» in the staff bot), so the owner can run everything
by buttons while away: system status, switches for the customer agent / the voice / the phone calls, the gold price,
the premium-customers list and the calls to them, a backup sent to the chat, and a restart.
No AI here: every button reads or writes the shop database directly. Only linked officials reach it."""
import datetime as dt
import os
import re
import subprocess
import threading
import time

START = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))

OPTIONS = [("🩺 حالة النظام", "c:st"), ("🤖 وكيل الزبائن", "c:ai"), ("🎙️ الصوت للزبائن", "c:vo"),
           ("📞 المكالمات", "c:ph"), ("💰 تحديث سعر الذهب", "c:pr"), ("🖼️ صور الواجهة", "c:hero"), ("⭐ العملاء المميزين", "c:vip"),
           ("📣 اتصل بالمميزين", "c:call"), ("💾 نسخة احتياطية", "c:bk"), ("🔄 إعادة تشغيل", "c:rs"),
           ("📘 الأوامر", "c:help")]
INTRO = "⚙️ التحكم: كل شي في النظام من هنا. اختر من تحت."
HELP = ("كل شي بالأزرار. وللي يحب الكتابة، هذي أوامر اختيارية:\n"
        "/price 52000 51000  تحديث سعر جرام 21 (البيع ثم الشراء)\n"
        "/vip add الاسم 77xxxxxxx  إضافة عميل مميز\n"
        "/vip del 77xxxxxxx  حذف عميل مميز\n"
        "/vip  قائمة المميزين\n"
        "/call الاسم 77xxxxxxx  اتصال واحد (نزول عادي)\n"
        "/call الاسم 77xxxxxxx قوي  اتصال واحد (نزول قوي)\n"
        "/status  حالة النظام\n"
        "والأزرار في «⚙️ التحكم» تسوي الباقي.")

_bulk = {"running": False, "done": 0, "total": 0, "kind": "", "stop": False}


def _git():
    try:
        out = subprocess.run(["git", "-C", HERE, "log", "-1", "--format=%h %cd", "--date=format:%m-%d %H:%M"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return out or "?"
    except Exception:
        return "?"


def _on(x):
    return "شغّال ✅" if x else "موقف ⛔"


def kb(app):
    rows = [OPTIONS[i:i + 2] for i in range(0, len(OPTIONS), 2)]
    return {"inline_keyboard": [[{"text": t, "callback_data": cb} for t, cb in row] for row in rows]}


def _back(extra=None):
    rows = list(extra or [])
    rows.append([{"text": "↩️ رجوع للتحكم", "callback_data": "c:menu"}])
    return {"inline_keyboard": rows}


def status(app):
    s = app.store
    ai = s.setting("ai", {}) or {}
    vo = s.setting("voice", {}) or {}
    ph = app.phone.cfg()
    d_ai, m_ai = app.agent._spent()
    try:
        d_vo = app.voice._spent_voice_today()
    except Exception:
        d_vo = 0.0
    today = dt.date.today().isoformat()
    month = dt.date.today().replace(day=1).isoformat()
    pd = s.one("SELECT COALESCE(SUM(cost),0) c, COUNT(*) n FROM phone_calls WHERE day=?", (today,))
    pm = s.one("SELECT COALESCE(SUM(cost),0) c FROM phone_calls WHERE day>=?", (month,))
    p = s.current_prices()
    price = ("{:,.0f} بيع / {:,.0f} شراء · آخر تحديث {}".format(float(p["k21_sell"]), float(p["k21_buy"]), str(p["created_at"])[:16])
             if p else "غير مسجل")
    up = int(time.time() - START)
    vip = s.setting("vip", []) or []
    lines = [
        "🩺 حالة النظام",
        f"النسخة: {_git()} · شغّال من {up // 3600} ساعة و{up % 3600 // 60} دقيقة",
        f"الرابط: {app.public_url or 'غير معروف'}",
        f"وكيل الزبائن: {_on(ai.get('enabled') and ai.get('api_key'))}" + ("" if ai.get("api_key") else " (المفتاح ناقص)"),
        f"الصوت للزبائن: {_on(vo.get('public'))}" + (" · وضع التجربة" if vo.get("test_mode", True) else ""),
        f"المكالمات: {_on(ph.get('enabled'))} · اليوم {pd['n']} من {ph.get('per_day')}",
        f"سعر جرام 21: {price}",
        f"العملاء المميزين: {len(vip)}",
        "",
        "💵 الصرف (دولار):",
        f"الوكيل: اليوم {d_ai:.2f} · الشهر {m_ai:.2f} (السقف {ai.get('daily_cap_usd', '?')} باليوم، {ai.get('monthly_cap_usd', '?')} بالشهر)",
        f"الصوت: اليوم {d_vo:.2f}",
        f"المكالمات: اليوم {float(pd['c']):.2f} · الشهر {float(pm['c']):.2f}",
        f"آخر نسخة احتياطية: {s.setting('last_backup_date', 'ما فيه')}",
    ]
    if _bulk["running"]:
        lines.append(f"📣 اتصال المميزين شغّال: {_bulk['done']} من {_bulk['total']}")
    return "\n".join(lines)


def toggle(app, what):
    """Flip a switch; returns the new state text."""
    s = app.store
    with app.lock:
        if what == "ai":
            c = dict(s.setting("ai", {}) or {})
            c["enabled"] = not c.get("enabled")
            s.set_setting("ai", c)
            on = c["enabled"]
            name = "وكيل الزبائن (الموقع والواتساب)"
        elif what == "vo":
            c = dict(s.setting("voice", {}) or {})
            c["public"] = not c.get("public")
            s.set_setting("voice", c)
            on = c["public"]
            name = "الصوت للزبائن في الموقع"
        else:
            c = dict(s.setting("phone", {}) or {})
            cur = app.phone.cfg().get("enabled", True)
            c["enabled"] = not cur
            s.set_setting("phone", c)
            on = c["enabled"]
            name = "المكالمات"
        s.db.commit()
    return f"{name}: {_on(on)}"


def state_view(app, what):
    s = app.store
    if what == "ai":
        on, name, note = bool((s.setting("ai", {}) or {}).get("enabled")), "🤖 وكيل الزبائن", "يرد على الزبائن في الموقع (والواتساب لما ينربط)."
    elif what == "vo":
        on, name, note = bool((s.setting("voice", {}) or {}).get("public")), "🎙️ الصوت للزبائن", "زر الكلام بالصوت في الموقع للزبائن."
    else:
        on, name, note = bool(app.phone.cfg().get("enabled", True)), "📞 المكالمات", "اتصال المستشار بالعملاء المميزين."
    btn = ("⛔ وقّفه" if on else "✅ شغّله")
    return f"{name}: {_on(on)}\n{note}", _back([[{"text": btn, "callback_data": "c:t" + what}]])


def set_price(app, text):
    nums = [float(x.replace(",", "")) for x in re.findall(r"[\d,]+(?:\.\d+)?", text or "")]
    if len(nums) < 2:
        return "اكتب: /price سعر_البيع سعر_الشراء\nمثال: /price 52000 51000"
    sell, buy = nums[0], nums[1]
    if buy > sell:
        sell, buy = buy, sell
    with app.lock:
        owner = app.store.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")["id"]
        app.store.set_prices(owner, sell, buy)
        app.store.db.commit()
    return "✅ تحدّث سعر جرام 21: بيع {:,.0f} · شراء {:,.0f}\nالموقع والوكيل والمكالمات يستخدمونه الحين.".format(sell, buy)


def num(text):
    """A price typed in a message: 52000, 52,000 or ٥٢٠٠٠ -> 52000.0 (None if it is not a number)."""
    t = (text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")).replace(",", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def save_price(app, buy, sell):
    with app.lock:
        owner = app.store.one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")["id"]
        app.store.set_prices(owner, sell, buy)
        app.store.db.commit()
    return "✅ تحدّث سعر جرام 21:\nالشراء {:,.0f}\nالبيع {:,.0f}\nالموقع والوكيل والمكالمات يستخدمونه الحين.".format(buy, sell)


def hero_view(app):
    h = list(app.store.setting("hero", []) or [])
    h += [""] * (3 - len(h))
    lines = ["🖼️ صور الواجهة (الثلاث اللي تتغير فوق في الموقع):"]
    for i in range(3):
        lines.append(f"{i + 1}. " + ("صورة خاصة ✅" if h[i] else "من صور القطع (تلقائي)"))
    lines.append("\nاضغط على رقم الصورة، وبعدها أرسل الصورة الجديدة.")
    rows = [[{"text": f"🔁 الصورة {i + 1}", "callback_data": f"c:h{i + 1}"} for i in range(3)],
            [{"text": "↩️ رجّعها كلها تلقائي", "callback_data": "c:h0"}]]
    return "\n".join(lines), _back(rows)


def set_hero(app, slot, name):
    with app.lock:
        h = list(app.store.setting("hero", []) or [])
        h += [""] * (3 - len(h))
        h[slot] = name
        app.store.set_setting("hero", h[:3])
        app.store.db.commit()


def vip_list(app):
    return list(app.store.setting("vip", []) or [])


def yemen_phone(text):
    """771234567 / 0771234567 / 967771234567 / +967 77 123 4567 / Arabic digits -> +967771234567 (None if not Yemeni)."""
    from phone import norm_phone
    t = (text or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    d = re.sub(r"[^\d+]", "", t)
    if re.fullmatch(r"07\d{8}", d):
        d = d[1:]
    p = norm_phone(d)
    return p if p and re.fullmatch(r"\+9677\d{8}", p) else None


def vip_view(app):
    """The premium list as buttons: tap a customer to call or remove him, «➕ إضافة عميل» to add."""
    v = vip_list(app)
    rows = [[{"text": f"👤 {r['name']}", "callback_data": f"c:v{i}"}] for i, r in enumerate(v[:40])]
    rows.append([{"text": "➕ إضافة عميل", "callback_data": "c:va"}])
    text = (f"⭐ العملاء المميزين ({len(v)}). اضغط على أي عميل تتصل عليه أو تحذفه." if v
            else "⭐ العملاء المميزين: القائمة فاضية. اضغط «➕ إضافة عميل».")
    return text, _back(rows)


def vip_one(app, i):
    v = vip_list(app)
    if i >= len(v):
        return vip_view(app)
    r = v[i]
    return (f"👤 {r['name']}\n📱 {r['phone']}",
            _back([[{"text": "📞 اتصل (نزول عادي)", "callback_data": f"c:vn{i}"}, {"text": "📞 اتصل (نزول قوي)", "callback_data": f"c:vs{i}"}],
                   [{"text": "❌ احذفه", "callback_data": f"c:vd{i}"}, {"text": "⭐ القائمة", "callback_data": "c:vip"}]]))


def known_name(app, phone):
    """The customer's name from the shop's own records (customers, invoices, reservations), matched by the last 9 digits."""
    tail = re.sub(r"\D", "", phone or "")[-9:]
    if len(tail) < 9:
        return None
    s = app.store
    for sql in ("SELECT name n, phone p FROM customers", "SELECT customer_name n, customer_phone p FROM invoices ORDER BY created_at DESC",
                "SELECT customer_name n, customer_phone p FROM reservations ORDER BY created_at DESC"):
        try:
            for r in s.q(sql + (" LIMIT 5000" if "ORDER" in sql else "")):
                if r["n"] and r["p"] and re.sub(r"\D", "", r["p"])[-9:] == tail:
                    return str(r["n"]).strip()[:40]
        except Exception:
            continue
    return None


def vip_add(app, name, phone):
    with app.lock:
        v = [r for r in vip_list(app) if r["phone"] != phone] + [{"name": name.strip()[:40], "phone": phone}]
        app.store.set_setting("vip", v)
        app.store.db.commit()
    return len(v)


def vip_remove(app, i):
    with app.lock:
        v = vip_list(app)
        if i < len(v):
            r = v.pop(i)
            app.store.set_setting("vip", v)
            app.store.db.commit()
            return r["name"]
    return None


def vip_cmd(app, text):
    from phone import norm_phone
    parts = (text or "").split()
    if len(parts) < 2:
        return vip_view(app)[0]
    op = parts[1].lower()
    with app.lock:
        v = vip_list(app)
        if op in ("add", "اضف", "أضف") and len(parts) >= 4:
            ph = norm_phone(parts[-1])
            name = " ".join(parts[2:-1]).strip()[:40]
            if not ph or not ph.startswith("+967") or not name:
                return "اكتب اسم ورقم يمني صحيح: /vip add محمد علي 771234567"
            v = [r for r in v if r["phone"] != ph] + [{"name": name, "phone": ph}]
            app.store.set_setting("vip", v)
            app.store.db.commit()
            return f"✅ انضاف {name} ({ph}). العدد الحين {len(v)}."
        if op in ("del", "حذف", "rm") and len(parts) >= 3:
            ph = norm_phone(parts[2])
            n = len(v)
            v = [r for r in v if r["phone"] != ph]
            app.store.set_setting("vip", v)
            app.store.db.commit()
            return "✅ انحذف." if len(v) < n else "ما لقيت هذا الرقم في القائمة."
    return vip_view(app)[0]


def one_call(app, text):
    parts = (text or "").split()[1:]
    kind = "normal"
    if parts and parts[-1] in ("قوي", "strong"):
        kind = "strong"
        parts = parts[:-1]
    if len(parts) < 2:
        return "اكتب: /call الاسم 77xxxxxxx (وأضف «قوي» لو النزول قوي)"
    r = app.phone.call(" ".join(parts[:-1]), parts[-1], kind, by_user="telegram")
    return "📞 بدأ الاتصال. يوصلك ملخص المكالمة هنا لما تخلص." if r.get("ok") else "ما بدأ الاتصال: " + str(r.get("why"))


def bulk_view(app):
    v = vip_list(app)
    if _bulk["running"]:
        return (f"📣 الاتصال شغّال: {_bulk['done']} من {_bulk['total']} ({'نزول قوي' if _bulk['kind'] == 'strong' else 'نزول عادي'}).",
                _back([[{"text": "⏹️ وقّف الاتصال", "callback_data": "c:cstop"}]]))
    if not v:
        return "📣 ما فيه عملاء مميزين. أضفهم أول من «⭐ العملاء المميزين».", _back()
    n10, n20 = min(10, len(v)), min(20, len(v))
    return (f"📣 اتصل بالمميزين (المسجلين {len(v)}).\nالمكالمات وحدة ورا وحدة، كل مكالمة أقل من دقيقتين.\n"
            f"التكلفة تقريباً: {n10} مكالمة ≈ {n10 * 0.39:.1f}$ · {n20} مكالمة ≈ {n20 * 0.39:.1f}$ بالكثير.",
            _back([[{"text": f"⬇️ نزول عادي ({n10})", "callback_data": "c:cn"}, {"text": f"⬇️⬇️ نزول قوي ({n20})", "callback_data": "c:cs"}]]))


def bulk_confirm(kind, app):
    n = min(10 if kind == "normal" else 20, len(vip_list(app)))
    lab = "نزول عادي" if kind == "normal" else "نزول قوي"
    return (f"متأكد؟ بيتصل على {n} عميل ({lab}).",
            _back([[{"text": "نعم، ابدأ", "callback_data": "c:cy" + ("n" if kind == "normal" else "s")}, {"text": "لا", "callback_data": "c:call"}]]))


def bulk_start(app, kind, notify):
    if _bulk["running"]:
        return "الاتصال شغّال من قبل."
    v = vip_list(app)[:10 if kind == "normal" else 20]
    _bulk.update({"running": True, "done": 0, "total": len(v), "kind": kind, "stop": False})

    def run():
        ok = 0
        try:
            for r in v:
                if _bulk["stop"]:
                    break
                res = app.phone.call(r["name"], r["phone"], kind, by_user="telegram-bulk")
                if res.get("ok"):
                    ok += 1
                    t0 = time.time()
                    while time.time() - t0 < 240:          # one call at a time: the webhook matches the latest dialing call
                        time.sleep(5)
                        row = app.store.one("SELECT status FROM phone_calls WHERE id=?", (res["id"],))
                        app.phone.recent(1)                  # closes a call that never reached the advisor
                        if not row or row["status"] not in ("dialing", "ringing", "answered", "active"):
                            break
                else:
                    notify(f"ما انتصل على {r['name']}: {res.get('why')}")
                    if "حد المكالمات" in str(res.get("why")) or "أدخل" in str(res.get("why")) or "مفتاح" in str(res.get("why")):
                        break
                _bulk["done"] += 1
                time.sleep(8)
        finally:
            _bulk["running"] = False
            notify(f"📣 خلص الاتصال بالمميزين: {ok} مكالمة بدأت من {len(v)}.")
    threading.Thread(target=run, daemon=True).start()
    return f"📣 بدأ الاتصال على {len(v)} عميل، وحدة ورا وحدة. يوصلك ملخص كل مكالمة هنا."


def backup(app):
    with app.lock:
        path = app.store.backup()
        app.store.set_setting("last_backup_date", dt.date.today().isoformat())
        app.store.db.commit()
    return path


def restart_later():
    """The server starts itself again in place (same process, same arguments), so it comes back whatever runs it."""
    import sys

    def go():
        time.sleep(2)
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=go, daemon=True).start()

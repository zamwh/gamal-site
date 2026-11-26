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
    "public": False,              # False: only signed-in staff see the microphone (the owner's test phase)
    "model": "gpt-live-1",
    "voice": "cedar",             # a calm male voice; dropped automatically if OpenAI does not offer it
    "per_customer_usd": 0.10,     # the most one customer can cost in a day
    "buyer_usd": 0.25,            # ... once he is buying (asked to buy, opened the purchase step)
    "daily_usd": 1.5,             # all voice calls in a day
    "price_per_min": 0.05,        # OpenAI's price for the voice layer, billed per second
    "min_billed_s": 15,           # OpenAI bills at least this much for every opening
    "close_after_ms": 2500,       # quiet (customer and assistant) this long -> the call closes until he speaks again
    "max_call_s": 240,            # one opening never runs longer than this
    "max_live": 3,                # calls open at the same moment, for the whole shop
    "opens_per_10min": 10,        # openings per customer in ten minutes
    "ack_delay_ms": 600,          # pause before "one moment" while the shop's assistant looks (OpenAI allows 0-800)
}

GOLD_KNOWLEDGE = """معرفة عامة عن الذهب تقدر تقولها بنفسك (بدون أي رقم من أرقام المحل):
- عيار 21 يعني 21 جزء ذهب من 24، تقريباً 87.5٪ ذهب. عيار 24 أنقى وأطرى، و18 أقسى وفيه ذهب أقل. ذهبنا كله عيار 21، ومعه جنيهات ذهب.
- سعر الذهب يتغير كل يوم مع السوق العالمي وسعر الصرف، والمحل يحدد سعره اليومي. سعر البيع أعلى من سعر الشراء، وهذا طبيعي في كل محلات الذهب.
- لو بيشتري: يقارن على نفس الأساس (العيار والوزن والسعر النهائي)، ويطلب الوزن قدامه، وياخذ فاتورة فيها العيار والوزن ويحتفظ بها لأنها تنفعه لو باع بعدين. وما ينصح يشتري فوق ميزانيته؛ فيه قطع أخف بنفس الروح.
- لو هدفه الادخار، الجنيهات أنسب من المشغولات لأنها أسهل في البيع. ولو للبس والمناسبة، يختار اللي يعجبه ويناسب ميزانيته.
- لو بيبيع ذهبه: ينظفه ويجيب فاتورته لو عنده. السعر يعتمد على العيار والوزن وحالة الذهب، والتقييم النهائي في المحل.
- ما نسوي تبديل ذهب بذهب. يقدر يبيع ذهبه للمحل نقد، ويشتري اللي يعجبه.
- الحفظ: كل قطعة في كيس لحالها عشان ما تنخدش، بعيد عن العطور والمنظفات والكلور. تنظيف خفيف بماء دافي وصابون وفرشاة ناعمة، وتنشيف زين."""

PERSONA = """أنت «مستشار جمال المشرقي»، بيّاع ذهب بصوتك في موقع محل «جمال المشرقي للذهب والمجوهرات»، بجوار البوابة الرئيسية لمركز جرعان، إب.
الشخصية: رجل هادي وواثق، لهجة يمنية بيضاء محترمة، جمل قصيرة، سرعة متوسطة. تخاطب الزبون بصيغة المذكر العامة. بيّاع شاطر يبذل جهده بصدق، وكأنه بصف الزبون، مو موظف كول سنتر.

القاعدة الأهم: أي شي عن القطع والأسعار والأوزان والتوفر والطلبات والسياسات (الشراء، العربون، التبديل، الإرجاع، الإصلاح، التقسيط، الخصم، الدوام، الموقع) ما تقوله من عندك أبداً: اطلب من الخلفية في كل مرة، وانتظر نتيجتها، وقلها بصوتك بنفس المعنى والأرقام كما هي بالضبط. لا تخترع رقم ولا قطعة ولا وعد. القطع اللي تقترحها الخلفية تطلع للزبون على الشاشة.
وأنت تنتظر الخلفية قل كلمة قصيرة طبيعية مثل «لحظة أشوف لك»، بدون حشو.

ممنوع: ذكر فروع (المحل واحد)، كلمة «صالة» أو «مغتربين» أو «زيارة خاصة»، أي ذكر لقريبات الزبون، الاستعجال أو «آخر قطعة»، أي خصم أو تقسيط أو تبديل أو إرجاع من عندك، وذكر المصنعية أو تفصيل السعر (المصنعية داخلية؛ السعر نهائي وشامل كل شي على سعر ذهب اليوم).
لو سأل عن خصم أو يبغى يكلم شخص: فريق المبيعات على الواتساب، والزر على الشاشة.
لو ما فهمت كلامه: قل بصراحة «ما فهمت عليك زين، ممكن تعيدها؟». ولو تكرر مرتين، اقترح عليه يكتب طلبه في المحادثة.
لو قاطعك: اسكت فوراً واسمعه.
لما يبغى يشتري: أعد التفاصيل اللي جات من الخلفية (القطعة وسعرها) وأكدها معه، وقل إن زر الشراء أو الحجز على الشاشة. ما تأكد دفع ولا حجز بنفسك.

""" + GOLD_KNOWLEDGE

GREETING = "البداية: ترحيب قصير وسؤال واحد بس، مثل: «حياك الله في جمال المشرقي. تجهز لمناسبة، ولا تدور على شي معيّن؟»"
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

    def _live_cost(self, row, now, c):
        """What an open call has cost so far: at least the minimum OpenAI bills for an opening."""
        return max(float(c["min_billed_s"]), now - float(row["started"])) * self._per_s(c)

    def _budget_left(self, who, c, extra=0.0, lab=False):
        spent, buyer = self._spent_by(who)
        cap = float(c["buyer_usd"] if (buyer or lab) else c["per_customer_usd"])   # staff testing: the buyer's cap
        day_left = float(c["daily_usd"]) - self._spent_voice_today()
        return max(0.0, min(cap - spent, day_left) - extra), buyer

    # ---- who may use it now
    def status(self, visitor, ip, lab):
        c = self.cfg()
        out = {"on": False, "close_after_ms": c["close_after_ms"], "lab": bool(lab)}
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

    def _instructions(self, session, resume):
        hist = self._history(session)
        parts = [PERSONA, RESUME if resume else GREETING]
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

    def open(self, visitor, session, sdp, ip, lab, resume=False):
        c = self.cfg()
        session = re.sub(r"[^A-Za-z0-9_-]", "", session or "")[:40]
        who = self._who(visitor, ip)
        if not sdp or len(sdp) > 30000 or not session:
            return {"ok": False, "why": "bad"}
        st = self.status(visitor, ip, lab)
        if not st["on"]:
            return {"ok": False, "why": st.get("why"), "say": BUSY}
        now = time.time()
        with self.lock:
            live = self.store.one("SELECT COUNT(*) n FROM voice_calls WHERE ended IS NULL AND last_beat>?", (now - 30,))["n"]
            recent = self.store.one("SELECT COUNT(*) n FROM voice_calls WHERE visitor=? AND started>?", (who, now - 600))["n"]
        if live >= int(c["max_live"]):
            return {"ok": False, "why": "busy", "say": BUSY}
        if recent >= int(c["opens_per_10min"]):
            return {"ok": False, "why": "rate", "say": BUSY}
        key = self.agent.cfg().get("api_key")
        try:
            ack = max(0, min(800, int(c.get("ack_delay_ms", 600))))        # OpenAI accepts 0 to 800
        except Exception:
            ack = 600
        sess = {"model": c["model"], "instructions": self._instructions(session, resume),
                "delegation": {"type": "client", "acknowledgement_delay_ms": ack}}
        if c.get("voice"):
            sess["audio"] = {"output": {"voice": c["voice"]}}
        code, d = self._post(key, {"session": sess, "transport": {"type": "webrtc", "sdp": sdp}})
        dropped = []
        for _ in range(2):                         # an optional setting OpenAI refuses: drop it and try again, once each
            if code != 400:
                break
            err = json.dumps(d).lower()
            if "audio" in sess and "voice" in err:
                sess.pop("audio"); dropped.append("voice")          # a voice name it does not offer: its default voice
            elif "acknowledgement_delay_ms" in err and "acknowledgement_delay_ms" in sess["delegation"]:
                sess["delegation"].pop("acknowledgement_delay_ms"); dropped.append("ack")
            else:
                break
            code, d = self._post(key, {"session": sess, "transport": {"type": "webrtc", "sdp": sdp}})
        if dropped and code in (200, 201):
            self._warn(0, "اشتغلت المكالمة بعد ما شلت إعداد رفضه OpenAI: " + "، ".join(dropped), ok=True)
        if code not in (200, 201) or not (d.get("transport") or {}).get("sdp"):
            msg = ((d.get("error") or {}).get("message") or "")[:300]
            self._warn(code, msg)
            return {"ok": False, "why": "openai", "code": code, "detail": msg if lab else "", "say": BUSY}
        cid = secrets.token_hex(8)
        with self.lock, self.app.lock:
            self.store.db.execute("INSERT INTO voice_calls (id,visitor,session,ip,day,started,last_beat,lab,oai_id,resumed) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (cid, who, session, (ip or "")[:60], self._today(), now, now, 1 if lab else 0,
                                   (d.get("session") or {}).get("id"), 1 if resume else 0))
            self.store.db.commit()
        left = max(0.0, st["budget_s"] * self._per_s(c))
        return {"ok": True, "call": cid, "sdp": d["transport"]["sdp"], "budget_s": int(left / self._per_s(c)),
                "close_after_ms": c["close_after_ms"], "max_call_s": c["max_call_s"]}

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

    def beat(self, cid):
        c = self.cfg()
        row = self._row(cid)
        if not row or row["ended"]:
            return {"ok": False, "left_s": 0}
        now = time.time()
        with self.lock, self.app.lock:
            self.store.db.execute("UPDATE voice_calls SET last_beat=? WHERE id=?", (now, row["id"]))
            self.store.db.commit()
        return {"ok": True, "left_s": self._left_s(row, now, c)}

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
        for k in ("offer", "handoff"):
            if k in res:
                out[k] = res[k]
        return out

    # ---- end of a call
    def close(self, cid, usage=None, reason="end"):
        c = self.cfg()
        with self.lock:
            row = self._row(cid)
            if not row or row["ended"]:
                return {"ok": True}
            now = time.time()
            end = now if reason != "stale" else min(now, float(row["last_beat"]) + 10)
            billed = max(float(c["min_billed_s"]), end - float(row["started"]))
            cost = round(billed * self._per_s(c), 5)
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
        return {"ok": True, "billed_s": round(billed, 1), "cost": cost}

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
                "price_per_min": c["price_per_min"], "public": c["public"]}

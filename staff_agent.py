"""The shop's internal agent: the owner asks it about sales, stock, reservations, demand, the website and AI cost.
Read-only by design: every tool reads the database; nothing here can sell, edit, delete or change a setting.
Numbers come from the tools (SQL), never from the model's head."""
import datetime as dt, json, os, re, sqlite3, urllib.error, urllib.request

PROMPT = """أنت "وكيل جمال المشرقي": مساعد داخلي لصاحب المحل والإدارة، تجاوب عن المحل من قاعدة البيانات مباشرة.
- كل رقم تقوله لازم يجي من أداة. لا تقدّر ولا تخمّن ولا تحسب من راسك. إذا الأداة ما رجعت الرقم قل ما عندي.
- ردود قصيرة ومرتبة بالعربي: الرقم أولاً، ثم سطر أو سطرين تفسير إذا يفيد. استخدم أسطر قصيرة بدل الجداول الطويلة.
- العملة ريال يمني، والوزن بالجرام. التواريخ بتوقيت المحل.
- "اليوم" و"أمس" و"هذا الأسبوع" و"هذا الشهر": حوّلها لتواريخ وأرسلها للأدوات.
- أنت للقراءة فقط: ما تقدر تبيع ولا تعدل ولا تحذف ولا تغيّر سعر. إذا طُلب منك قل إنه يتم من البرنامج أو لوحة الإدارة.
- إذا السؤال يحتاج تحليلاً ما تغطيه الأدوات الجاهزة، استخدم run_sql بجملة SELECT واحدة.
- لا تذكر أرقام هواتف أو أسماء زبائن إلا إذا سُئلت عن طلب أو حجز معيّن.
- بدون إيموجي."""

TOOLS = [
    {"type": "function", "function": {"name": "sales_summary", "description": "مبيعات فترة: عدد الفواتير، الإجمالي، الجرامات، خصم المصنعية، حسب الفرع وحسب اليوم.",
     "parameters": {"type": "object", "properties": {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "top_sold", "description": "القطع المباعة في فترة مرتبة بالقيمة، مع المبيعات بالوزن (قطع غير مسجلة).",
     "parameters": {"type": "object", "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "stock_summary", "description": "المخزون الحالي: عدد القطع والجرامات حسب النوع والفرع، والمحجوز، والمعروض في الموقع.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "reservations", "description": "الحجوزات حسب الحالة (pending بانتظار التأكيد، active مؤكدة، الكل).",
     "parameters": {"type": "object", "properties": {"status": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "demand", "description": "طلبات الزبائن غير المتوفرة اللي سجلها المستشار، مجمعة حسب النوع.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "website_and_ai", "description": "زوار الموقع ومشاهدات القطع ومحادثات المستشار وتكلفة الذكاء الاصطناعي في فترة.",
     "parameters": {"type": "object", "properties": {"date_from": {"type": "string"}, "date_to": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "piece_interest", "description": "اهتمام الزبائن: كم شخص فتح كل قطعة في الموقع وكم حافظها، وكم ضغط «أبغى مثلها» تحت القطع المباعة في القناة، وتفاعلات القناة. تفيد لمعرفة وش يطلبه الناس ووش ينشرى.",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "prices_today", "description": "سعر الذهب المعتمد اليوم وأسعار الصرف.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "find_piece", "description": "بحث عن قطعة برمزها أو اسمها: حالتها وسعرها وفرعها.",
     "parameters": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}},
    {"type": "function", "function": {"name": "run_sql", "description": "استعلام قراءة فقط (SELECT واحد) لأي سؤال ما تغطيه الأدوات. الجداول: invoices(number,kind,branch_id,total,status,created_at,customer_name), invoice_items(invoice_id,piece_id,description,karat,weight,gram_price,making,line_total,making_discount), pieces(code,type,title,karat,weight,making_value,status,branch_id,show_online,created_at), branches(id,name), reservations(number,piece_id,status,deposit,quoted_price,created_at), demand_requests(category,description,budget,status,ts), chat_logs(session,ts,role,content), prices(k21_sell,k21_buy,created_at).",
     "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}},
]


class StaffAgent:
    def __init__(self, store, lock, analytics=None, sales_agent=None):
        self.store, self.lock, self.analytics, self.sales = store, lock, analytics, sales_agent
        self.history = {}           # per staff user/chat: last turns

    # ---------- tools (read-only)
    def _range(self, a, b):
        today = dt.date.today()
        a = a or today.isoformat()
        b = b or a
        dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        return a, b

    def tool(self, name, args):
        s = self.store
        if name == "sales_summary":
            a, b = self._range(args.get("date_from"), args.get("date_to"))
            w = "kind='sale' AND status='ok' AND substr(created_at,1,10) BETWEEN ? AND ?"
            tot = s.one(f"SELECT COUNT(*) invoices, COALESCE(SUM(total),0) total FROM invoices WHERE {w}", (a, b))
            g = s.one(f"""SELECT COALESCE(SUM(ii.weight),0) grams, COALESCE(SUM(ii.making_discount),0) making_discount,
                         COALESCE(SUM(ii.making),0) making FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE {w.replace('kind', 'i.kind').replace('status', 'i.status').replace('created_at', 'i.created_at')}""", (a, b))
            by_b = s.q(f"""SELECT b.name branch, COUNT(*) invoices, COALESCE(SUM(i.total),0) total FROM invoices i JOIN branches b ON b.id=i.branch_id
                          WHERE {w.replace('kind', 'i.kind').replace('status', 'i.status').replace('created_at', 'i.created_at')} GROUP BY b.name""", (a, b))
            by_d = s.q(f"SELECT substr(created_at,1,10) day, COUNT(*) invoices, SUM(total) total FROM invoices WHERE {w} GROUP BY day ORDER BY day", (a, b))
            buy = s.one("""SELECT COUNT(*) n, COALESCE(SUM(total),0) total FROM invoices WHERE kind='purchase' AND status='ok'
                           AND substr(created_at,1,10) BETWEEN ? AND ?""", (a, b))
            return {"from": a, "to": b, **tot, **g, "by_branch": by_b, "by_day": by_d, "gold_bought_from_customers": buy}
        if name == "top_sold":
            a, b = self._range(args.get("date_from"), args.get("date_to"))
            return {"from": a, "to": b, "items": s.q("""SELECT ii.description, p.code, ii.weight, ii.line_total, p.category, i.created_at
                     FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id LEFT JOIN pieces p ON p.id=ii.piece_id
                     WHERE i.kind='sale' AND i.status='ok' AND substr(i.created_at,1,10) BETWEEN ? AND ?
                     ORDER BY ii.line_total DESC LIMIT ?""", (a, b, int(args.get("limit") or 10)))}
        if name == "stock_summary":
            return {"by_kind": s.q("""SELECT type kind, COUNT(*) pieces, ROUND(SUM(weight),2) grams FROM pieces
                                      WHERE status='available' GROUP BY type ORDER BY pieces DESC"""),
                    "by_branch": s.q("""SELECT b.name branch, COUNT(*) pieces, ROUND(SUM(p.weight),2) grams FROM pieces p
                                        JOIN branches b ON b.id=p.branch_id WHERE p.status='available' GROUP BY b.name"""),
                    "reserved": s.one("SELECT COUNT(*) n FROM pieces WHERE status='reserved'")["n"],
                    "online": sum(1 for p in s.q("SELECT * FROM pieces WHERE status='available'") if __import__("core").online_ok(s, p)),
                    "total_available": s.one("SELECT COUNT(*) n, ROUND(COALESCE(SUM(weight),0),2) g FROM pieces WHERE status='available'")}
        if name == "reservations":
            st = args.get("status")
            sql = """SELECT r.number, p.code, COALESCE(p.title,p.type) piece, r.status, r.deposit, r.quoted_price, r.created_at, r.expires_at
                     FROM reservations r JOIN pieces p ON p.id=r.piece_id"""
            rows = s.q(sql + (" WHERE r.status=?" if st and st != "all" else "") + " ORDER BY r.created_at DESC LIMIT 30",
                       (st,) if st and st != "all" else ())
            return {"count": len(rows), "rows": rows}
        if name == "demand":
            return {"open_by_category": s.q("""SELECT category, COUNT(*) n, ROUND(AVG(NULLIF(budget,0))) avg_budget FROM demand_requests
                                              WHERE status='open' GROUP BY category ORDER BY n DESC"""),
                    "latest": s.q("SELECT ts, category, description, budget FROM demand_requests ORDER BY id DESC LIMIT 10")}
        if name == "website_and_ai":
            a, b = self._range(args.get("date_from"), args.get("date_to"))
            out = {"from": a, "to": b}
            if self.analytics:          # the analytics methods take their own lock (taking it here too froze the thread)
                k = self.analytics.overview(a, b)["kpi"]
                out["website"] = {x: k.get(x) for x in ("visitors", "sessions", "piece_views", "ai_chat", "shortlist", "requests", "whatsapp")}
                out["ai_cost_usd"] = round(self.analytics._one("SELECT COALESCE(SUM(cost),0) c FROM ai_usage WHERE day BETWEEN ? AND ?", (a, b))["c"], 4)
                out["ai_messages"] = self.analytics._one("SELECT COUNT(*) n FROM ai_usage WHERE day BETWEEN ? AND ?", (a, b))["n"]
            out["handoffs"] = s.one("SELECT COUNT(*) n FROM handoffs WHERE substr(ts,1,10) BETWEEN ? AND ?", (a, b))["n"]
            return out
        if name == "piece_interest":
            pi = self.analytics.piece_interest() if self.analytics else {}
            rows = []
            for p in s.q("""SELECT p.code, COALESCE(p.title,p.type) name, p.weight, b.name branch FROM pieces p
                            JOIN branches b ON b.id=p.branch_id WHERE p.status='available'"""):
                v = pi.get(p["code"]) or [0, 0]
                rows.append(dict(p, opened_by=v[0], saved_by=v[1]))
            rows.sort(key=lambda r: (r["opened_by"] + 3 * r["saved_by"]), reverse=True)
            return {"note": "opened_by = أشخاص فتحوا القطعة، saved_by = أشخاص حافظينها الحين، من يوم نزلت. "
                            "want_like_it = ضغطوا «أبغى مثلها» تحت قطعة انباعت في القناة. channel_reactions = تفاعلات القناة على المنشور",
                    "pieces": rows[:int(args.get("limit") or 15)],
                    "want_like_it": s.q("""SELECT p.code, COALESCE(p.title,p.type) name, p.type kind, COUNT(*) n FROM channel_likes l
                                           JOIN pieces p ON p.code=l.code GROUP BY p.code ORDER BY n DESC LIMIT 10"""),
                    "channel_reactions": s.q("""SELECT p.code, COALESCE(p.title,p.type) name, p.status, c.reactions FROM channel_posts c
                                               JOIN pieces p ON p.code=c.code WHERE c.reactions>0 ORDER BY c.reactions DESC LIMIT 10""")}
        if name == "prices_today":
            return s.current_prices() or {"error": "ما فيه سعر معتمد اليوم"}
        if name == "find_piece":
            q = str(args.get("q", "")).strip()
            rows = s.q("""SELECT p.code, COALESCE(p.title,p.type) name, p.weight, p.status, p.show_online, b.name branch
                          FROM pieces p JOIN branches b ON b.id=p.branch_id WHERE p.code=? OR p.title LIKE ? OR p.type LIKE ? LIMIT 10""",
                       (q.upper(), f"%{q}%", f"%{q}%"))
            pi = self.analytics.piece_interest([r["code"] for r in rows]) if self.analytics else {}
            for r in rows:
                r["opened_by"], r["saved_by"] = (pi.get(r["code"]) or [0, 0])
            return {"rows": rows}
        if name == "run_sql":
            sql = str(args.get("sql", "")).strip().rstrip(";")
            if not re.match(r"(?is)^\s*(select|with)\b", sql) or ";" in sql or re.search(r"(?i)\b(attach|pragma|insert|update|delete|drop|alter|create|replace|vacuum)\b", sql):
                return {"error": "مسموح استعلام قراءة واحد فقط (SELECT)"}
            if re.search(r"(?i)\b(users|sessions_tokens|settings)\b", sql):
                return {"error": "هذا الجدول محمي"}
            db = sqlite3.connect(f"file:{self.store.path}?mode=ro", uri=True)       # read-only connection
            db.row_factory = sqlite3.Row
            try:
                cur = db.execute(sql)
                rows = [dict(r) for r in cur.fetchmany(200)]
                return {"rows": rows, "n": len(rows)}
            except Exception as e:
                return {"error": str(e)[:200]}
            finally:
                db.close()
        return {"error": "unknown tool"}

    # ---------- conversation
    def ask(self, who, message):
        cfg = self.sales.cfg() if self.sales else {}
        if not cfg.get("api_key"):
            return "الذكاء الاصطناعي غير مفعّل: ضع المفتاح في الإعدادات."
        today = dt.date.today()
        hist = self.history.setdefault(who, [])
        msgs = [{"role": "system", "content": PROMPT + f"\nتاريخ اليوم: {today.isoformat()} ({['الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد'][today.weekday()]})."}] \
            + hist[-10:] + [{"role": "user", "content": message[:1500]}]
        text = ""
        for rnd in range(6):
            payload = {"model": cfg.get("model") or "gpt-6-luna", "messages": msgs, "tools": TOOLS,
                       "max_completion_tokens": 1500, "reasoning_effort": "none"}
            if rnd == 5:
                payload["tool_choice"] = "none"
            r = self._post(cfg, payload)
            m = r["choices"][0]["message"]
            calls = m.get("tool_calls") or []
            if not calls:
                text = m.get("content") or ""
                break
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
            for c in calls:
                try:
                    with self.lock:
                        res = self.tool(c["function"]["name"], json.loads(c["function"].get("arguments") or "{}"))
                except Exception as e:
                    res = {"error": str(e)[:200]}
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res, ensure_ascii=False, default=str)[:12000]})
        text = (text or "ما قدرت أطلع جواب الحين.").replace("**", "")
        hist += [{"role": "user", "content": message[:1500]}, {"role": "assistant", "content": text[:2000]}]
        self.history[who] = hist[-20:]
        return text

    def _post(self, cfg, payload):
        def go(p):
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", json.dumps(p).encode(),
                                         {"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=90).read())
        try:
            return go(payload)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            if e.code == 400 and "reasoning_effort" in body:
                return go({k: v for k, v in payload.items() if k != "reasoning_effort"})
            raise

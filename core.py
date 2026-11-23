# -*- coding: utf-8 -*-
"""Core logic for the Gamal Almshrqi Gold & Jewelry branch program.

Everything here works offline on a local SQLite file. Demo and live data
live in two separate database files, so resetting the demo can never touch
real data.
"""
import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import secrets
import shutil
import sqlite3
import uuid

APP_NAME = "GamalAlmshrqi"
BASE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME)

KARATS = (18, 21, 24)
STATUSES = ("available", "reserved", "sold", "transfer", "inactive")
ROLES = ("owner", "manager", "accountant", "seller")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS branches (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT, phone TEXT, map_url TEXT);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL, branch_id TEXT, salt TEXT NOT NULL, pw_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (
  id TEXT PRIMARY KEY, k21_sell REAL, k21_buy REAL, k18_sell REAL, k18_buy REAL,
  k24_sell REAL, k24_buy REAL, pound_sell REAL, pound_buy REAL,
  usd_rate REAL, sar_rate REAL, user_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pieces (
  id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, type TEXT NOT NULL,
  karat INTEGER NOT NULL, weight REAL NOT NULL, making_mode TEXT NOT NULL,
  making_value REAL NOT NULL DEFAULT 0, category TEXT NOT NULL DEFAULT 'new',
  cost_per_gram REAL, branch_id TEXT NOT NULL, status TEXT NOT NULL,
  show_online INTEGER NOT NULL DEFAULT 1, notes TEXT, created_by TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices (
  id TEXT PRIMARY KEY, number TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
  branch_id TEXT NOT NULL, user_id TEXT NOT NULL, customer_name TEXT,
  customer_phone TEXT, customer_id_note TEXT, subtotal REAL NOT NULL,
  adjust_amount REAL NOT NULL DEFAULT 0, adjust_reason TEXT, deposit REAL NOT NULL DEFAULT 0,
  total REAL NOT NULL, signature TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ok',
  void_reason TEXT, voided_by TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoice_items (
  id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL, piece_id TEXT, description TEXT NOT NULL,
  karat INTEGER NOT NULL, weight REAL NOT NULL, base_gram_price REAL NOT NULL,
  gram_price REAL NOT NULL, making REAL NOT NULL DEFAULT 0, line_total REAL NOT NULL,
  as_scrap INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS scrap_lots (
  id TEXT PRIMARY KEY, karat INTEGER NOT NULL, weight REAL NOT NULL,
  cost_per_gram REAL NOT NULL, branch_id TEXT NOT NULL, invoice_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id TEXT, action TEXT NOT NULL,
  entity TEXT, entity_id TEXT, details TEXT);
CREATE TABLE IF NOT EXISTS reservations (
  id TEXT PRIMARY KEY, number TEXT UNIQUE NOT NULL, piece_id TEXT NOT NULL, customer_name TEXT NOT NULL,
  customer_phone TEXT NOT NULL, quoted_price REAL NOT NULL, deposit REAL NOT NULL, status TEXT NOT NULL,
  policy_text TEXT NOT NULL, accepted_at TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT,
  confirmed_by TEXT, expires_at TEXT, closed_at TEXT, close_note TEXT);
CREATE INDEX IF NOT EXISTS ix_pieces_status ON pieces(status);
CREATE INDEX IF NOT EXISTS ix_inv_created ON invoices(created_at);
"""


class GoldError(Exception):
    """Business-rule error with an Arabic message meant for the user."""


def now():
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def new_id():
    return uuid.uuid4().hex


def _hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


# ---------------------------------------------------------------- amounts in words
_ONES = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة", "عشرة",
         "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر", "ستة عشر", "سبعة عشر",
         "ثمانية عشر", "تسعة عشر"]
_TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_HUNDREDS = ["", "مائة", "مائتان", "ثلاثمائة", "أربعمائة", "خمسمائة", "ستمائة", "سبعمائة",
             "ثمانمائة", "تسعمائة"]
_SCALES = [(10 ** 9, "مليار", "ملياران", "مليارات", "ملياراً"),
           (10 ** 6, "مليون", "مليونان", "ملايين", "مليوناً"),
           (10 ** 3, "ألف", "ألفان", "آلاف", "ألفاً")]


def _under_1000(n):
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if r:
        if r < 20:
            parts.append(_ONES[r])
        else:
            t, o = divmod(r, 10)
            parts.append((_ONES[o] + " و" if o else "") + _TENS[t])
    return " و".join(parts)


def number_to_arabic_words(n):
    n = int(round(n))
    if n == 0:
        return "صفر"
    parts = []
    for value, one, two, plural, tanween in _SCALES:
        count, n = divmod(n, value)
        if not count:
            continue
        last2 = count % 100
        if count == 1:
            parts.append(one)
        elif count == 2:
            parts.append(two)
        elif 3 <= last2 <= 10:
            parts.append(_under_1000(count) + " " + plural)
        elif 11 <= last2 <= 99:
            parts.append(_under_1000(count) + " " + tanween)
        else:
            parts.append(_under_1000(count) + " " + one)
    if n:
        parts.append(_under_1000(n))
    return " و".join(parts)


def amount_in_words(n):
    return "فقط " + number_to_arabic_words(n) + " ريال يمني لا غير"


# ---------------------------------------------------------------- codes
def barcode_svg(code):
    import barcode
    from barcode.writer import SVGWriter
    buf = io.BytesIO()
    barcode.get("code128", code, writer=SVGWriter()).write(
        buf, {"module_height": 8, "module_width": 0.25, "quiet_zone": 1, "write_text": False})
    return buf.getvalue().decode()


def qr_svg(text):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def svg_data_uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ---------------------------------------------------------------- store
class Store:
    def __init__(self, mode="demo", base_dir=BASE_DIR):
        if mode not in ("demo", "live"):
            raise ValueError(mode)
        self.mode = mode
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self.path = os.path.join(base_dir, f"{mode}.db")
        fresh = not os.path.exists(self.path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        if fresh:
            self._init_settings()
            if mode == "demo":
                seed_demo(self)

    # ---- helpers
    def q(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None

    def setting(self, key, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_setting(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))
        self.db.commit()

    def log(self, user_id, action, entity=None, entity_id=None, details=None):
        self.db.execute("INSERT INTO audit (ts,user_id,action,entity,entity_id,details) VALUES (?,?,?,?,?,?)",
                        (now(), user_id, action, entity, entity_id,
                         json.dumps(details, ensure_ascii=False) if details is not None else None))

    MIGRATIONS = {
        "pieces": [("title", "TEXT"), ("photos", "TEXT NOT NULL DEFAULT '[]'"), ("style", "TEXT"),
                   ("occasion", "TEXT"), ("description", "TEXT")],
        "reservations": [("kind", "TEXT NOT NULL DEFAULT 'deposit'"), ("payer_name", "TEXT"),
                         ("receipt", "TEXT"), ("amount", "REAL"), ("source", "TEXT"), ("session", "TEXT")],
    }

    def _migrate(self):
        for table, cols in self.MIGRATIONS.items():
            have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        if self.one("SELECT 1 FROM settings WHERE key='secret'") and self.setting("payments") is None:
            self._init_web_settings()
        self.db.commit()

    def _init_web_settings(self):
        self.set_setting("payments", [])          # [{"name": "بنك ...", "holder": "...", "account": "..."}]
        self.set_setting("links", {"tiktok": "https://www.tiktok.com/@almashraqi.gold8", "facebook": "https://www.facebook.com/share/1JkbaD2t5t/", "instagram": "https://www.instagram.com/almashreqi_gold", "whatsapp": "+967770088801"})
        self.set_setting("purchase", {"lock_note": "السعر يثبت بسعر الذهب وقت وصول التحويل كاملاً"})

    def _init_settings(self):
        self.set_setting("secret", secrets.token_hex(32))
        self.set_setting("shop", {"name": "جمال المشرقي للذهب والمجوهرات",
                                  "name_en": "Gamal Almshrqi Gold and Jewelry",
                                  "phone": "", "address": "إب - اليمن"})
        self.set_setting("min_scrap_margin", 0)
        self.set_setting("pound_weight", 8)
        self.set_setting("invoice_seq", 0)
        self.set_setting("piece_seq", 0)
        self.set_setting("reservation", {"hours": 24, "deposit_pct": 10, "free_cancel_hours": 2,
                                         "noshow_deduct_pct": 10, "noshow_min": 0, "refund_days": 3})
        self._init_web_settings()

    # ---- users
    def create_user(self, username, name, role, password, branch_id=None, by=None):
        if role not in ROLES:
            raise GoldError("رتبة غير معروفة")
        if len(password) < 6:
            raise GoldError("كلمة السر لازم تكون 6 أحرف على الأقل")
        salt = secrets.token_hex(16)
        uid = new_id()
        try:
            self.db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,1,?)",
                            (uid, username.strip(), name.strip(), role, branch_id, salt,
                             _hash_pw(password, salt), now()))
        except sqlite3.IntegrityError:
            raise GoldError("اسم المستخدم موجود مسبقاً")
        self.log(by, "user_create", "user", uid, {"username": username, "role": role})
        self.db.commit()
        return uid

    def login(self, username, password):
        u = self.one("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),))
        if not u or not hmac.compare_digest(u["pw_hash"], _hash_pw(password, u["salt"])):
            self.log(None, "login_failed", "user", None, {"username": username})
            self.db.commit()
            raise GoldError("اسم المستخدم أو كلمة السر غير صحيحة")
        self.log(u["id"], "login", "user", u["id"])
        self.db.commit()
        return {k: u[k] for k in ("id", "username", "name", "role", "branch_id")}

    def user(self, uid):
        u = self.one("SELECT id,username,name,role,branch_id FROM users WHERE id=? AND active=1", (uid,))
        if not u:
            raise GoldError("المستخدم غير موجود")
        return u

    def require(self, uid, *roles):
        u = self.user(uid)
        if u["role"] not in roles:
            raise GoldError("ما عندك صلاحية لهذه العملية")
        return u

    # ---- prices
    def current_prices(self):
        return self.one("SELECT * FROM prices ORDER BY created_at DESC, rowid DESC LIMIT 1")

    def set_prices(self, uid, k21_sell, k21_buy, k18_sell=None, k18_buy=None, k24_sell=None,
                   k24_buy=None, pound_sell=None, pound_buy=None, usd_rate=None, sar_rate=None):
        self.require(uid, "owner", "manager")
        k21_sell, k21_buy = float(k21_sell), float(k21_buy)
        if k21_sell <= 0 or k21_buy <= 0:
            raise GoldError("أدخل سعر بيع وشراء صحيح لعيار 21")
        derive = lambda base, k: round(base * k / 21)
        pw = float(self.setting("pound_weight", 8))
        row = {
            "k21_sell": k21_sell, "k21_buy": k21_buy,
            "k18_sell": float(k18_sell) if k18_sell else derive(k21_sell, 18),
            "k18_buy": float(k18_buy) if k18_buy else derive(k21_buy, 18),
            "k24_sell": float(k24_sell) if k24_sell else derive(k21_sell, 24),
            "k24_buy": float(k24_buy) if k24_buy else derive(k21_buy, 24),
            "pound_sell": float(pound_sell) if pound_sell else round(k21_sell * pw),
            "pound_buy": float(pound_buy) if pound_buy else round(k21_buy * pw),
            "usd_rate": float(usd_rate) if usd_rate else None,
            "sar_rate": float(sar_rate) if sar_rate else None,
        }
        pid = new_id()
        self.db.execute("""INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pid, row["k21_sell"], row["k21_buy"], row["k18_sell"], row["k18_buy"],
                         row["k24_sell"], row["k24_buy"], row["pound_sell"], row["pound_buy"],
                         row["usd_rate"], row["sar_rate"], uid, now()))
        self.log(uid, "prices_set", "prices", pid, row)
        self.db.commit()
        return self.current_prices()

    def gram_price(self, karat, side="sell"):
        p = self.current_prices()
        if not p:
            raise GoldError("ما فيه سعر لليوم. أدخل سعر الذهب أولاً")
        if int(karat) not in KARATS:
            raise GoldError("عيار غير مدعوم")
        return float(p[f"k{int(karat)}_{side}"])

    # ---- branches
    def branches(self):
        return self.q("SELECT * FROM branches ORDER BY rowid")

    # ---- pieces
    def _next_code(self):
        seq = int(self.setting("piece_seq", 0)) + 1
        self.set_setting("piece_seq", seq)
        prefix = "D" if self.mode == "demo" else "G"
        return f"{prefix}{seq:06d}"

    def add_piece(self, uid, type_, karat, weight, making_mode, making_value, branch_id,
                  category="new", cost_per_gram=None, notes="", show_online=True,
                  title="", photos=None, style="", occasion="", description=""):
        u = self.user(uid)
        if int(karat) not in KARATS:
            raise GoldError("عيار غير مدعوم")
        weight = float(weight)
        if weight <= 0:
            raise GoldError("الوزن لازم يكون أكبر من صفر")
        if making_mode not in ("gram", "fixed"):
            raise GoldError("نوع المصنعية غير صحيح")
        if not self.one("SELECT id FROM branches WHERE id=?", (branch_id,)):
            raise GoldError("الفرع غير موجود")
        if u["role"] == "seller" and u["branch_id"] and u["branch_id"] != branch_id:
            raise GoldError("البائع يضيف قطعاً لفرعه فقط")
        pid, code, ts = new_id(), self._next_code(), now()
        self.db.execute("""INSERT INTO pieces (id, code, type, karat, weight, making_mode, making_value, category,
                           cost_per_gram, branch_id, status, show_online, notes, created_by, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pid, code, type_.strip(), int(karat), round(weight, 3), making_mode,
                         float(making_value or 0), category, cost_per_gram, branch_id, "available",
                         1 if show_online else 0, notes, uid, ts, ts))
        self.db.execute("UPDATE pieces SET title=?, photos=?, style=?, occasion=?, description=? WHERE id=?",
                        ((title or "").strip() or None, json.dumps(list(photos or []), ensure_ascii=False),
                         style or None, occasion or None, (description or "").strip() or None, pid))
        self.log(uid, "piece_add", "piece", pid, {"code": code, "weight": weight, "karat": karat})
        self.db.commit()
        return self.piece(code)

    def set_piece_media(self, uid, code, title=None, photos=None, style=None, occasion=None,
                        description=None, show_online=None):
        self.require(uid, "owner", "manager")
        p = self.piece(code)
        fields = {"title": title, "style": style, "occasion": occasion, "description": description}
        for k, v in fields.items():
            if v is not None:
                self.db.execute(f"UPDATE pieces SET {k}=? WHERE id=?", (v.strip() or None, p["id"]))
        if photos is not None:
            self.db.execute("UPDATE pieces SET photos=? WHERE id=?", (json.dumps(list(photos)), p["id"]))
        if show_online is not None:
            self.db.execute("UPDATE pieces SET show_online=? WHERE id=?", (1 if show_online else 0, p["id"]))
        self.db.execute("UPDATE pieces SET updated_at=? WHERE id=?", (now(), p["id"]))
        self.log(uid, "piece_media", "piece", p["id"], {"code": p["code"]})
        self.db.commit()
        return self.piece(code)

    def piece(self, code):
        p = self.one("""SELECT p.*, b.name AS branch_name FROM pieces p
                        JOIN branches b ON b.id=p.branch_id WHERE p.code=?""", (code.strip().upper(),))
        if not p:
            raise GoldError("ما فيه قطعة بهذا الرقم")
        return p

    def piece_price(self, p, gram_price=None):
        gp = float(gram_price) if gram_price is not None else self.gram_price(p["karat"], "sell")
        making = p["making_value"] * p["weight"] if p["making_mode"] == "gram" else p["making_value"]
        return {"gram_price": gp, "making": round(making), "total": round(p["weight"] * gp + making)}

    def list_pieces(self, status=None, branch_id=None, search=""):
        sql = ("SELECT p.*, b.name AS branch_name FROM pieces p JOIN branches b ON b.id=p.branch_id "
               "WHERE 1=1")
        args = []
        if status:
            sql += " AND p.status=?"
            args.append(status)
        if branch_id:
            sql += " AND p.branch_id=?"
            args.append(branch_id)
        if search:
            sql += " AND (p.code LIKE ? OR p.type LIKE ? OR p.notes LIKE ?)"
            args += [f"%{search}%"] * 3
        sql += " ORDER BY p.created_at DESC LIMIT 500"
        rows = self.q(sql, args)
        has_price = self.current_prices() is not None
        for r in rows:
            r["price"] = self.piece_price(r)["total"] if has_price else None
        return rows

    def set_piece_status(self, uid, code, status, reason=""):
        self.require(uid, "owner", "manager")
        if status not in ("available", "inactive"):
            raise GoldError("يمكن فقط التفعيل أو الإيقاف من هنا")
        p = self.piece(code)
        if p["status"] == "sold":
            raise GoldError("القطعة مباعة ومقفولة")
        self.db.execute("UPDATE pieces SET status=?, updated_at=? WHERE id=?", (status, now(), p["id"]))
        self.log(uid, "piece_status", "piece", p["id"], {"from": p["status"], "to": status, "reason": reason})
        self.db.commit()

    def transfer_piece(self, uid, code, to_branch):
        self.require(uid, "owner", "manager")
        p = self.piece(code)
        if p["status"] != "available":
            raise GoldError("لا يمكن نقل قطعة غير متاحة")
        if p["branch_id"] == to_branch:
            raise GoldError("القطعة في نفس الفرع")
        self.db.execute("UPDATE pieces SET branch_id=?, updated_at=? WHERE id=?", (to_branch, now(), p["id"]))
        self.log(uid, "piece_transfer", "piece", p["id"], {"from": p["branch_id"], "to": to_branch})
        self.db.commit()

    # ---- invoices
    def _next_invoice_no(self, kind):
        seq = int(self.setting("invoice_seq", 0)) + 1
        self.set_setting("invoice_seq", seq)
        prefix = {"sale": "S", "purchase": "P"}[kind]
        return f"{'D' if self.mode == 'demo' else ''}{prefix}{seq:06d}"

    def _sign(self, number, total, created_at):
        msg = f"{number}|{int(round(total))}|{created_at}".encode()
        return hmac.new(bytes.fromhex(self.setting("secret")), msg, hashlib.sha256).hexdigest()[:16]

    def verify_signature(self, number, total, created_at, sig):
        return hmac.compare_digest(self._sign(number, total, created_at), sig)

    def create_sale(self, uid, items, customer_name="", customer_phone="", adjust_amount=0,
                    adjust_reason="", deposit=0):
        """items: [{"code": str, "gram_price": optional override}]"""
        u = self.user(uid)
        if not items:
            raise GoldError("الفاتورة فاضية")
        codes = [i["code"].strip().upper() for i in items]
        if len(set(codes)) != len(codes):
            raise GoldError("نفس القطعة مكررة في الفاتورة")
        adjust_amount = float(adjust_amount or 0)
        if adjust_amount and not adjust_reason.strip():
            raise GoldError("اكتب سبب الإضافة أو الخصم")
        branch_id, lines, subtotal, reserved_numbers, auto_deposit = None, [], 0, [], 0
        min_margin = float(self.setting("min_scrap_margin", 0))
        for item in items:
            p = self.piece(item["code"])
            res = self.reservation_for_piece(p["id"]) if p["status"] == "reserved" else None
            if p["status"] != "available" and not res:
                raise GoldError(f"القطعة {p['code']} غير متاحة للبيع ({p['status']})")
            if res:
                reserved_numbers.append(res["number"])
                auto_deposit += res["deposit"]
            if u["role"] == "seller" and u["branch_id"] and p["branch_id"] != u["branch_id"]:
                raise GoldError(f"القطعة {p['code']} في فرع آخر")
            branch_id = branch_id or p["branch_id"]
            if p["branch_id"] != branch_id:
                raise GoldError("كل قطع الفاتورة لازم تكون من نفس الفرع")
            base = self.gram_price(p["karat"], "sell")
            override = item.get("gram_price")
            gp = float(override) if override not in (None, "") else base
            if res and res["kind"] == "full":   # paid in full by transfer: price locked at transfer time
                making = p["making_value"] * p["weight"] if p["making_mode"] == "gram" else p["making_value"]
                gp = (res["quoted_price"] - making) / p["weight"]
                base = gp
            if gp <= 0:
                raise GoldError("سعر الجرام غير صحيح")
            if p["category"] == "clean_scrap" and p["cost_per_gram"] is not None and not (res and res["kind"] == "full"):
                floor = p["cost_per_gram"] + min_margin
                if gp < floor and u["role"] != "owner":
                    raise GoldError(f"سعر الجرام للقطعة {p['code']} أقل من الحد الأدنى المسموح")
            price = self.piece_price(p, gp)
            lines.append((p, base, price))
            subtotal += price["total"]
        deposit = float(deposit or 0) + auto_deposit
        total = round(subtotal + adjust_amount - deposit)
        if total < 0:
            raise GoldError("الإجمالي لا يمكن أن يكون بالسالب")
        inv_id, ts = new_id(), now()
        number = self._next_invoice_no("sale")
        sig = self._sign(number, total, ts)
        self.db.execute("""INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (inv_id, number, "sale", branch_id, uid, customer_name, customer_phone, None,
                         subtotal, adjust_amount, adjust_reason, deposit, total, sig, "ok",
                         None, None, ts))
        for p, base, price in lines:
            self.db.execute("""INSERT INTO invoice_items VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
                            (new_id(), inv_id, p["id"], p["type"], p["karat"], p["weight"], base,
                             price["gram_price"], price["making"], price["total"]))
            self.db.execute("UPDATE pieces SET status='sold', updated_at=? WHERE id=?", (ts, p["id"]))
            if price["gram_price"] != base:
                self.log(uid, "price_override", "piece", p["id"],
                         {"invoice": number, "base": base, "used": price["gram_price"]})
        for rn in reserved_numbers:
            self.db.execute("UPDATE reservations SET status='completed', closed_at=?, close_note=? WHERE number=?",
                            (ts, number, rn))
        if adjust_amount:
            self.log(uid, "invoice_adjust", "invoice", inv_id,
                     {"amount": adjust_amount, "reason": adjust_reason})
        self.log(uid, "sale", "invoice", inv_id, {"number": number, "total": total})
        self.db.commit()
        return self.invoice(number)

    def create_purchase(self, uid, items, customer_name, customer_phone="", customer_id_note=""):
        """Buy used gold. items: [{"type","karat","weight","gram_price", "as_scrap": bool}]"""
        u = self.user(uid)
        if not customer_name.strip():
            raise GoldError("اسم البائع مطلوب في سند الشراء")
        if not items:
            raise GoldError("السند فاضي")
        branch_id = u["branch_id"] or self.branches()[0]["id"]
        inv_id, ts = new_id(), now()
        number = self._next_invoice_no("purchase")
        subtotal, rows = 0, []
        for it in items:
            k, w = int(it["karat"]), float(it["weight"])
            if k not in KARATS or w <= 0:
                raise GoldError("بيانات القطعة غير صحيحة")
            base = self.gram_price(k, "buy")
            gp = float(it.get("gram_price") or base)
            line = round(w * gp)
            subtotal += line
            rows.append((it, k, w, base, gp, line))
        sig = self._sign(number, subtotal, ts)
        self.db.execute("""INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (inv_id, number, "purchase", branch_id, uid, customer_name, customer_phone,
                         customer_id_note, subtotal, 0, None, 0, subtotal, sig, "ok", None, None, ts))
        for it, k, w, base, gp, line in rows:
            as_scrap = bool(it.get("as_scrap", True))
            self.db.execute("""INSERT INTO invoice_items VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                            (new_id(), inv_id, None, it.get("type") or "كسر", k, w, base, gp, 0, line,
                             1 if as_scrap else 0))
            if as_scrap:
                self.db.execute("INSERT INTO scrap_lots VALUES (?,?,?,?,?,?,?)",
                                (new_id(), k, w, gp, branch_id, inv_id, ts))
            else:
                self.add_piece(uid, it.get("type") or "قطعة مستعملة", k, w, "fixed", 0, branch_id,
                               category="clean_scrap", cost_per_gram=gp, notes=f"من سند {number}")
            if gp != base:
                self.log(uid, "price_override", "purchase", inv_id, {"base": base, "used": gp})
        self.log(uid, "purchase", "invoice", inv_id, {"number": number, "total": subtotal})
        self.db.commit()
        return self.invoice(number)

    def invoice(self, number):
        inv = self.one("""SELECT i.*, b.name AS branch_name, b.address AS branch_address,
                          b.phone AS branch_phone, u.name AS user_name FROM invoices i
                          JOIN branches b ON b.id=i.branch_id JOIN users u ON u.id=i.user_id
                          WHERE i.number=?""", (number,))
        if not inv:
            raise GoldError("الفاتورة غير موجودة")
        inv["items"] = self.q("""SELECT ii.*, p.code FROM invoice_items ii
                                 LEFT JOIN pieces p ON p.id=ii.piece_id WHERE invoice_id=?""", (inv["id"],))
        inv["words"] = amount_in_words(inv["total"])
        qr_text = f"GAM|{inv['number']}|{int(round(inv['total']))}|{inv['created_at']}|{inv['signature']}"
        inv["qr"] = svg_data_uri(qr_svg(qr_text))
        inv["shop"] = self.setting("shop")
        inv["demo"] = self.mode == "demo"
        return inv

    def list_invoices(self, kind=None, limit=200):
        sql = ("SELECT i.number,i.kind,i.total,i.status,i.created_at,i.customer_name,b.name AS branch_name,"
               "u.name AS user_name FROM invoices i JOIN branches b ON b.id=i.branch_id "
               "JOIN users u ON u.id=i.user_id")
        args = []
        if kind:
            sql += " WHERE i.kind=?"
            args.append(kind)
        return self.q(sql + " ORDER BY i.created_at DESC, i.rowid DESC LIMIT ?", args + [limit])

    def void_invoice(self, uid, number, reason):
        self.require(uid, "owner", "manager")
        if not reason.strip():
            raise GoldError("سبب الإلغاء مطلوب")
        inv = self.invoice(number)
        if inv["status"] == "void":
            raise GoldError("الفاتورة ملغاة مسبقاً")
        if inv["kind"] != "sale":
            raise GoldError("إلغاء سندات الشراء غير متاح في هذه النسخة")
        for it in inv["items"]:
            if it["piece_id"]:
                self.db.execute("UPDATE pieces SET status='available', updated_at=? WHERE id=?",
                                (now(), it["piece_id"]))
        self.db.execute("UPDATE invoices SET status='void', void_reason=?, voided_by=? WHERE id=?",
                        (reason, uid, inv["id"]))
        self.log(uid, "invoice_void", "invoice", inv["id"], {"number": number, "reason": reason})
        self.db.commit()

    # ---- reservations
    def policy_text(self, kind="deposit"):
        r = self.setting("reservation")
        if kind == "full":
            return ("شراء بتحويل كامل قيمة القطعة: يثبت السعر بسعر الذهب وقت التحويل، ولا يُعد الشراء رسمياً إلا بعد "
                    "مراجعة المحاسب لوصول المبلغ كاملاً. صورة الإيصال وحدها لا تكفي للتأكيد. بعد التأكيد تُحفظ القطعة باسمك "
                    "وتستلمها من الفرع بفاتورة رسمية موقعة من الطرفين. لا يوجد شحن. رسوم التحويل على العميل.")
        return (f"الحجز بعربون {r['deposit_pct']}% من قيمة القطعة يحفظها {r['hours']} ساعة من تأكيده ولا يثبّت سعر الذهب؛ "
                f"السعر النهائي بسعر الذهب يوم إتمام البيع ويُخصم منه العربون. لا يُعد الحجز مؤكداً إلا بعد مراجعة المحاسب "
                f"لوصول التحويل. الإلغاء خلال {r['free_cancel_hours']} ساعة من التأكيد يُرد فيه العربون كاملاً. "
                f"عند عدم الحضور أو الإلغاء بعد ذلك يُخصم {r['noshow_deduct_pct']}% من العربون (بحد أدنى {r['noshow_min']} ريال) "
                f"ويُرد الباقي خلال {r['refund_days']} أيام عمل، ورسوم التحويل على العميل. يمكن طلب التمديد. "
                f"الاستلام في الفرع فقط بفاتورة موقعة من الطرفين.")

    def request_reservation(self, code, customer_name, customer_phone, accepted, kind="deposit",
                            payer_name="", receipt="", source="web", session=""):
        if kind not in ("deposit", "full"):
            raise GoldError("نوع الطلب غير معروف")
        if not accepted:
            raise GoldError("لازم توافق على الشروط قبل التحويل")
        if not customer_name.strip() or len(customer_phone.strip()) < 7:
            raise GoldError("الاسم ورقم الجوال مطلوبان")
        if not payer_name.strip() or not receipt:
            raise GoldError("اكتب اسم المحوِّل وأرفق صورة إيصال التحويل")
        self.expire_reservations()
        p = self.piece(code)
        if p["status"] != "available" or not p["show_online"]:
            raise GoldError("القطعة غير متاحة حالياً")
        if self.one("SELECT 1 FROM reservations WHERE piece_id=? AND status='pending'", (p["id"],)):
            raise GoldError("يوجد طلب آخر على هذه القطعة قيد المراجعة")
        price = self.piece_price(p)["total"]
        pct = float(self.setting("reservation")["deposit_pct"])
        amount = price if kind == "full" else round(price * pct / 100)
        rid, ts = new_id(), now()
        seq = int(self.setting("res_seq", 0)) + 1
        self.set_setting("res_seq", seq)
        number = f"{'D' if self.mode == 'demo' else ''}{'P' if kind == 'full' else 'R'}{seq:05d}"
        self.db.execute("""INSERT INTO reservations (id, number, piece_id, customer_name, customer_phone, quoted_price,
                           deposit, status, policy_text, accepted_at, created_at, kind, payer_name, receipt, amount,
                           source, session) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (rid, number, p["id"], customer_name.strip()[:80], customer_phone.strip()[:20], price, amount,
                         "pending", self.policy_text(kind), ts, ts, kind, payer_name.strip()[:80], receipt, amount,
                         source[:10], (session or "")[:40]))
        self.log(None, "reservation_request", "reservation", rid, {"number": number, "code": p["code"], "kind": kind})
        self.db.commit()
        return {"number": number, "amount": amount, "price": price, "code": p["code"], "kind": kind}

    def confirm_reservation(self, uid, number):
        self.require(uid, "owner", "accountant")
        self.expire_reservations()
        r = self.one("SELECT * FROM reservations WHERE number=?", (number,))
        if not r or r["status"] != "pending":
            raise GoldError("الحجز غير موجود أو ليس بانتظار التأكيد")
        p = self.one("SELECT * FROM pieces WHERE id=?", (r["piece_id"],))
        if p["status"] != "available":
            raise GoldError("القطعة لم تعد متاحة؛ يجب رد العربون للعميل")
        ts = dt.datetime.now().replace(microsecond=0)
        exp = ts + dt.timedelta(hours=float(self.setting("reservation")["hours"]))
        if r["kind"] == "full":
            exp = None
        self.db.execute("UPDATE reservations SET status='active', confirmed_at=?, confirmed_by=?, expires_at=? WHERE id=?",
                        (ts.isoformat(sep=" "), uid, exp.isoformat(sep=" ") if exp else None, r["id"]))
        self.db.execute("UPDATE pieces SET status='reserved', updated_at=? WHERE id=?", (now(), p["id"]))
        self.log(uid, "reservation_confirm", "reservation", r["id"], {"number": number, "kind": r["kind"]})
        self.db.commit()

    def close_reservation(self, uid, number, status, note=""):
        self.require(uid, "owner", "manager", "accountant")
        if status not in ("cancelled", "extended"):
            raise GoldError("إجراء غير معروف")
        r = self.one("SELECT * FROM reservations WHERE number=?", (number,))
        if not r or r["status"] not in ("pending", "active"):
            raise GoldError("الحجز غير قابل للتعديل")
        if status == "extended":
            if r["status"] != "active" or r["kind"] == "full":
                raise GoldError("التمديد لحجوزات العربون المؤكدة فقط")
            exp = dt.datetime.fromisoformat(r["expires_at"]) + dt.timedelta(
                hours=float(self.setting("reservation")["hours"]))
            self.db.execute("UPDATE reservations SET expires_at=? WHERE id=?", (exp.isoformat(sep=" "), r["id"]))
        else:
            self.db.execute("UPDATE reservations SET status='cancelled', closed_at=?, close_note=? WHERE id=?",
                            (now(), note, r["id"]))
            if r["status"] == "active":
                self.db.execute("UPDATE pieces SET status='available', updated_at=? WHERE id=? AND status='reserved'",
                                (now(), r["piece_id"]))
        self.log(uid, "reservation_" + status, "reservation", r["id"], {"number": number, "note": note})
        self.db.commit()

    def expire_reservations(self):
        ts = now()
        for r in self.q("SELECT * FROM reservations WHERE status='active' AND expires_at IS NOT NULL AND expires_at<?", (ts,)):
            self.db.execute("UPDATE reservations SET status='expired', closed_at=? WHERE id=?", (ts, r["id"]))
            self.db.execute("UPDATE pieces SET status='available', updated_at=? WHERE id=? AND status='reserved'",
                            (ts, r["piece_id"]))
            self.log(None, "reservation_expired", "reservation", r["id"], {"number": r["number"]})
        self.db.commit()

    def list_reservations(self):
        self.expire_reservations()
        return self.q("""SELECT r.*, p.code, p.type, p.weight, p.karat, b.name AS branch_name FROM reservations r
                         JOIN pieces p ON p.id=r.piece_id JOIN branches b ON b.id=p.branch_id
                         ORDER BY r.created_at DESC LIMIT 200""")

    def reservation_for_piece(self, piece_id):
        return self.one("SELECT * FROM reservations WHERE piece_id=? AND status='active'", (piece_id,))

    # ---- labels
    def label(self, code):
        p = self.piece(code)
        return {"code": p["code"], "type": p["type"], "karat": p["karat"], "weight": p["weight"],
                "making_mode": p["making_mode"], "making_value": p["making_value"],
                "barcode": svg_data_uri(barcode_svg(p["code"])), "qr": svg_data_uri(qr_svg(p["code"]))}

    # ---- reports
    def dashboard(self):
        today = dt.date.today().isoformat()
        sales = self.one("""SELECT COUNT(*) n, COALESCE(SUM(total),0) amount FROM invoices
                            WHERE kind='sale' AND status='ok' AND created_at>=?""", (today,))
        grams = self.one("""SELECT COALESCE(SUM(ii.weight),0) g FROM invoice_items ii
                            JOIN invoices i ON i.id=ii.invoice_id
                            WHERE i.kind='sale' AND i.status='ok' AND i.created_at>=?""", (today,))
        bought = self.one("""SELECT COALESCE(SUM(ii.weight),0) g, COALESCE(SUM(ii.line_total),0) amount
                             FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
                             WHERE i.kind='purchase' AND i.created_at>=?""", (today,))
        stock = self.q("""SELECT karat, COUNT(*) n, ROUND(SUM(weight),2) g FROM pieces
                          WHERE status='available' GROUP BY karat ORDER BY karat""")
        by_branch = self.q("""SELECT b.name, COUNT(i.id) n, COALESCE(SUM(i.total),0) amount
                              FROM branches b LEFT JOIN invoices i ON i.branch_id=b.id AND i.kind='sale'
                              AND i.status='ok' AND i.created_at>=? GROUP BY b.id ORDER BY b.rowid""", (today,))
        scrap = self.q("SELECT karat, ROUND(SUM(weight),2) g FROM scrap_lots GROUP BY karat ORDER BY karat")
        return {"sales": sales, "grams_sold": grams["g"], "bought": bought, "stock": stock,
                "by_branch": by_branch, "scrap": scrap}

    def audit_log(self, limit=300):
        return self.q("""SELECT a.*, u.name AS user_name FROM audit a LEFT JOIN users u ON u.id=a.user_id
                         ORDER BY a.id DESC LIMIT ?""", (limit,))

    # ---- backup
    def backup(self, dest_dir=None):
        dest_dir = dest_dir or os.path.join(self.base_dir, "backups")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, f"{self.mode}-{dt.datetime.now():%Y%m%d-%H%M%S}.db")
        bk = sqlite3.connect(dest)
        self.db.backup(bk)
        bk.close()
        return dest

    def daily_backup_if_needed(self):
        last = self.setting("last_backup_date")
        today = dt.date.today().isoformat()
        if last != today:
            path = self.backup()
            self.set_setting("last_backup_date", today)
            return path
        return None

    def close(self):
        self.db.close()


def reset_demo(base_dir=BASE_DIR):
    """Delete and re-seed the demo database only. Never touches live.db."""
    path = os.path.join(base_dir, "demo.db")
    live = os.path.join(base_dir, "live.db")
    assert os.path.abspath(path) != os.path.abspath(live)
    if os.path.exists(path):
        os.remove(path)
    return Store("demo", base_dir)


def seed_demo(s):
    branches = [("الفرع الأول", "مركز جرعان — المحل رقم 6", "", ""),
                ("الفرع الثاني", "خط السبل — مركز وان مول، الدور الأول، المحل رقم 3", "", ""),
                ("الفرع الثالث", "بجوار البوابة الرئيسية لمركز جرعان", "", "")]
    ids = []
    for name, addr, phone, mp in branches:
        bid = new_id()
        s.db.execute("INSERT INTO branches VALUES (?,?,?,?,?)", (bid, name, addr, phone, mp))
        ids.append(bid)
    s.db.commit()
    owner = s.create_user("owner", "صاحب المحل (تجريبي)", "owner", "123456")
    s.create_user("manager", "مدير الفرع (تجريبي)", "manager", "123456", ids[0], by=owner)
    s.create_user("seller", "بائع (تجريبي)", "seller", "123456", ids[0], by=owner)
    s.create_user("accountant", "المحاسب (تجريبي)", "accountant", "123456", None, by=owner)
    s.set_prices(owner, 51500, 49500, usd_rate=535, sar_rate=140)
    s.set_prices(owner, 52000, 50000, usd_rate=535, sar_rate=140)
    s.set_setting("links", {"tiktok": "https://www.tiktok.com/@almashraqi.gold8", "facebook": "https://www.facebook.com/share/1JkbaD2t5t/", "instagram": "https://www.instagram.com/almashreqi_gold", "whatsapp": "+967770088801"})
    s.set_setting("payments", [{"name": "بنك الكريمي", "holder": "جمال المشرقي للذهب والمجوهرات", "account": "0000 0000 0000"}, {"name": "النجم للحوالات", "holder": "جمال المشرقي للذهب والمجوهرات", "account": "000000000"}, {"name": "محفظة جيب", "holder": "جمال المشرقي", "account": "770 000 000"}, {"name": "محفظة ون كاش", "holder": "جمال المشرقي", "account": "770 000 000"}])
    # demo pieces use the shop's real photos (assets/demo), copied into the demo media folder
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "demo")
    dst = os.path.join(s.base_dir, "media", s.mode)
    os.makedirs(dst, exist_ok=True)
    demo = [  # (photo, title, type, weight, making/gram, style, occasion, branch, description)
        ("set", "طقم عروس متكامل بالورد", "طقم", 148.6, 3000, "فخم", "عرس", 0,
         "طقم كامل: عقد بشراشيب، حلق، كف بخواتم، وحزام مدوّر."),
        ("bib", "عقد صدر شبك", "عقد", 96.4, 3000, "فخم", "عرس", 0, "عقد صدر عريض بتصميم الشبك والمعيّنات."),
        ("crescent", "طقم الهلال بالشراشيب", "طقم", 55.6, 3000, "كلاسيكي", "عرس", 1,
         "عقد بتعليقة هلال مزدوج وشراشيب، مع حلق."),
        ("chains", "طقم سلاسل بالمستطيل", "طقم", 38.5, 3000, "كلاسيكي", "خطوبة", 0,
         "عقد طويل بتعليقة مستطيلة متدرجة، مع حلق."),
        ("velvet", "عقد مجدول بالقطرات", "عقد", 58.2, 3000, "كلاسيكي", "عرس", 1,
         "عقد مجدول بثلاث قطرات مخرّمة، مع حلق."),
        ("collar", "كردان كرات مع أسورة", "عقد", 74.0, 3000, "فخم", "عرس", 2, "كردان عريض من الكرات المنقوشة مع أسورة."),
        ("flower", "طقم الوردة الطويل مع الحزام", "طقم", 120.0, 3000, "فخم", "عرس", 2,
         "عقد طويل بوردة وشراشيب، حزام بطبقات، وحلق."),
    ]
    for photo, title, typ, w, mk, style, occ, b, desc in demo:
        photos = []
        if os.path.exists(os.path.join(src, photo + ".jpg")):
            shutil.copyfile(os.path.join(src, photo + ".jpg"), os.path.join(dst, "demo_" + photo + ".jpg"))
            photos = ["demo_" + photo + ".jpg"]
        s.add_piece(owner, typ, 21, w, "gram", mk, ids[b], title=title, photos=photos, style=style, occasion=occ,
                    description=desc)
    s.add_piece(owner, "أسورة مستعملة نظيفة", 21, 9.6, "fixed", 0, ids[0], category="clean_scrap",
                cost_per_gram=49500, notes="كسر نظيف (تجريبي)", show_online=False)
    s.create_purchase(owner, [{"type": "كسر", "karat": 21, "weight": 6.2, "as_scrap": True}],
                      "بائع تجريبي", "770000098", "بطاقة شخصية")
    s.db.commit()

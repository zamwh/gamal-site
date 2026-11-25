# -*- coding: utf-8 -*-
"""The shop's Telegram channel, run by the bot on the server.

Linking: the owner makes a channel and adds the bot as an admin of it. Telegram tells the bot; when the person who
added it is a linked staff account the channel is linked on the spot, otherwise it waits for /channel from one.
Posting: a piece is posted by itself once it has its display (velvet) photo: at once when all three photos are in,
or after a quiet 10 minutes, so the website page has every photo by the time customers open it. At most one post a
minute. The post is one photo (Telegram allows no buttons under an album) with two buttons under it: the sales team
on WhatsApp (a ready message names the piece) and the piece's page on the website, where it can be bought.
Sold: the caption changes to "تم البيع" and the one button becomes «أبغى مثلها»: a customer shows interest with
one tap (counted once per person, no chat, no WhatsApp) and the owner sees what people want, to stock by it.
Emoji reactions on every post are counted too (Telegram sends the totals to the bot, a few minutes late).
The bot itself is for the shop's staff only; customers see the channel."""
import datetime as dt
import hashlib
import html
import json
import os
import re
import time
import urllib.parse

import core

QUIET_MIN = 10          # minutes without a new photo before a piece missing a photo is posted anyway
EVERY_S = 60            # one post a minute at most: the channel is never flooded
PAUSE_S = 15 * 60       # after Telegram refuses a post, wait before trying again
MAX_TRIES = 3


def _tg(store):
    return dict(store.setting("telegram", {}) or {})


def _put(store, key, value):
    c = _tg(store)
    if value is None:
        c.pop(key, None)
    else:
        c[key] = value
    store.set_setting("telegram", c)


def get(store):
    return dict(_tg(store).get("channel") or {})


def save(store, ch):
    _put(store, "channel", ch)


def pending(store):
    return dict(_tg(store).get("pending_channel") or {})


def set_pending(store, chat, by):
    _put(store, "pending_channel", {"id": chat["id"], "title": chat.get("title") or "", "username": chat.get("username") or "",
                                    "by": str(by), "at": core.now()})


def link(store, chat, by, can_post=True):
    old = get(store)
    same = old.get("id") == chat["id"]              # the same channel again (rights changed): keep its place
    ch = {"id": chat["id"], "title": chat.get("title") or old.get("title") or "", "username": chat.get("username") or "",
          "since": old.get("since") if same else core.now(), "auto": old.get("auto", True) if same else True,
          "by": str(by), "can_post": bool(can_post), "queue": list(old.get("queue") or []) if same else []}
    save(store, ch)
    _put(store, "pending_channel", None)
    return ch


def unlink(store):
    _put(store, "channel", None)


def set_auto(store, on):
    ch = get(store)
    if ch:
        ch["auto"] = bool(on)
        save(store, ch)
    return ch


def posted(store, code):
    return store.one("SELECT * FROM channel_posts WHERE code=?", (code,))


def status(store):
    ch, pe = get(store), pending(store)
    n = store.one("SELECT COUNT(*) n FROM channel_posts WHERE message_id>0")["n"]
    return {"linked": bool(ch.get("id")), "title": ch.get("title", ""), "username": ch.get("username", ""),
            "auto": ch.get("auto", True), "can_post": ch.get("can_post", True), "posted": n,
            "queued": len(ch.get("queue") or []), "last_error": ch.get("last_error"),
            "pending": pe.get("title") if pe.get("id") and pe.get("id") != ch.get("id") else None}


# ---------------- what to post
def _age_s(ts, now=None):
    try:
        t = time.mktime(time.strptime((ts or "")[:19], "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0
    return (now or time.time()) - t


def ready(p, now=None, quiet_min=QUIET_MIN):
    """Has its display photo, and either all three photos or no new photo for a while."""
    r = core.piece_roles(p)
    if not r.get("card"):
        return False
    return all(r.get(k) for k in core.PHOTO_ROLES) or _age_s(p["media_at"], now) >= quiet_min * 60


def _postable(store, p):
    return (p and p["status"] == "available" and p["show_online"] and not posted(store, p["code"])
            and any(core.piece_roles(p).values()))


def next_piece(store, now=None):
    """The one piece to post now, or None."""
    ch = get(store)
    if not ch.get("id") or (now or time.time()) < float(ch.get("pause_until") or 0):
        return None
    q = list(ch.get("queue") or [])
    while q:                                       # asked for by hand: "post what we have", /post
        p = store.one("SELECT * FROM pieces WHERE code=?", (q[0],))
        if _postable(store, p):
            break
        q.pop(0)
    if q != list(ch.get("queue") or []):
        ch["queue"] = q
        save(store, ch)
    if q:
        return store.one("SELECT * FROM pieces WHERE code=?", (q[0],))
    if not ch.get("auto", True):
        return None
    rows = store.q("""SELECT * FROM pieces WHERE status='available' AND show_online=1 AND COALESCE(media_at,'')>=?
                      AND code NOT IN (SELECT code FROM channel_posts) ORDER BY media_at""", (ch.get("since") or "",))
    return next((p for p in rows if ready(p, now)), None)


def seed_candidates(store, limit=10):
    """Pieces already on the site, for a channel that starts empty: new arrivals first, then the latest."""
    today = dt.date.today().isoformat()
    rows = store.q("""SELECT * FROM pieces WHERE status='available' AND show_online=1
                      AND code NOT IN (SELECT code FROM channel_posts)
                      ORDER BY (COALESCE(new_until,'')>=?) DESC, created_at DESC LIMIT 60""", (today,))
    return [p["code"] for p in rows if any(core.piece_roles(p).values())][:limit]


def live_posts(store):
    """Posts the bot thinks are in the channel and still offered (checked against Telegram before republishing)."""
    return store.q("SELECT * FROM channel_posts WHERE message_id>0 AND sold=0")


def forget(store, codes):
    """These posts are gone from the channel (deleted by hand) or never made it: the pieces can be posted again."""
    for c in codes:
        store.db.execute("DELETE FROM channel_posts WHERE code=?", (c,))
    store.db.execute("DELETE FROM channel_posts WHERE message_id=0")
    ch = get(store)
    if ch:
        ch["tries"], ch["pause_until"] = {}, 0
        save(store, ch)
    store.db.commit()


def enqueue(store, codes, front=False):
    ch = get(store)
    if not ch.get("id"):
        return 0
    q = [c for c in (ch.get("queue") or []) if c not in codes]
    ch["queue"] = (list(codes) + q) if front else (q + list(codes))
    save(store, ch)
    return len(codes)


def seed(store, limit=10):
    codes = seed_candidates(store, limit)[::-1]          # oldest first, so the newest ends up at the bottom
    return enqueue(store, codes)


# ---------------- the post
def _branch(store, p):
    b = store.one("SELECT name, address FROM branches WHERE id=?", (p["branch_id"],))
    if not b:
        return ""
    return b["name"] + (f": {b['address']}" if b["address"] else "")


def site_host_ok(store, host):
    """Only a real address of the shop's website may go into the channel's buttons (never one a request made up)."""
    h = (host or "").split(":")[0].lower()
    if re.fullmatch(r"[a-z0-9-]+\.trycloudflare\.com", h):
        return True
    return h in [str(d).strip().lower() for d in (store.setting("site_domains", []) or [])]


def wa_link(store, p):
    num = re.sub(r"\D", "", (store.setting("links", {}) or {}).get("whatsapp", "") or "")
    if not num:
        return None
    title = (p["title"] if "title" in p.keys() else None) or p["type"]
    msg = f"السلام عليكم، أبغى أستفسر عن القطعة «{title}» رقم {p['code']} من قناة التليجرام."
    return f"https://wa.me/{num}?text=" + urllib.parse.quote(msg)


def likes(store, code):
    return store.one("SELECT COUNT(*) n FROM channel_likes WHERE code=?", (code,))["n"]


def like_label(n):
    return "❤️ أبغى مثلها" + (f" · {n}" if n else "")


def add_like(store, code, user_id):
    """One tap of «أبغى مثلها»: counted once per person (kept as a one-way fingerprint, not the account)."""
    who = hashlib.sha256(f"{store.setting('secret', '') or ''}|{user_id}".encode()).hexdigest()[:20]
    cur = store.db.execute("INSERT OR IGNORE INTO channel_likes (code, who, ts) VALUES (?,?,?)", (code, who, core.now()))
    store.db.commit()
    return cur.rowcount == 1, likes(store, code)


def set_reactions(store, chat_id, message_id, total):
    store.db.execute("UPDATE channel_posts SET reactions=? WHERE chat_id=? AND message_id=?", (int(total), str(chat_id), int(message_id)))
    store.db.commit()


def buttons(store, p, base, sold=False):
    """Under the post: the sales team on WhatsApp and the piece on the website; once sold, «أبغى مثلها» only."""
    if sold:
        return {"inline_keyboard": [[{"text": like_label(likes(store, p["code"])), "callback_data": f"lk:{p['code']}"}]]}
    rows = []
    wa = wa_link(store, p)
    if wa:
        rows.append([{"text": "💬 تواصل مع فريق المبيعات", "url": wa}])
    if base:
        rows.append([{"text": "🛍️ اعرضها واشترِها من الموقع", "url": f"{base.rstrip('/')}/p/{p['code']}"}])
    return {"inline_keyboard": rows}


def _kb(markup):
    return json.dumps(markup, ensure_ascii=False, sort_keys=True)


def caption(store, p, sold=False):
    e = lambda t: html.escape(str(t or ""), quote=False)
    title = (p["title"] if "title" in p.keys() else None) or p["type"]
    new = core.showcase_state(p)["new"]
    head = ("تم البيع · " if sold else "وصل حديثاً · " if new else "") + title
    lines = [f"<b>{e(head)}</b>"]
    desc = ((p["description"] if "description" in p.keys() else "") or "").strip()
    if desc and not sold:
        lines.append(e(desc[:200]))
    lines.append(f"ذهب عيار {p['karat']} · الوزن {float(p['weight']):.2f} جرام")
    br = _branch(store, p)
    if br and not sold:
        lines.append(e(br))
    lines.append(f"رقم القطعة {e(p['code'])}")
    if sold:
        lines += ["", "عجبتك؟ اضغط «أبغى مثلها»، ورأيك يحدد البضاعة الجاية."]
    return "\n".join(lines)


def main_photo(store, p):
    """The post's one photo: the velvet display shot, else the original, else the close-up."""
    folder = os.path.join(store.base_dir, "media", store.mode)
    r = core.piece_roles(p)
    for k in ("card", "orig", "macro"):
        if r.get(k) and os.path.isfile(os.path.join(folder, r[k])):
            return os.path.join(folder, r[k])
    return None


def record(store, code, chat_id, message_id, markup):
    store.db.execute("INSERT OR REPLACE INTO channel_posts (code, chat_id, message_id, photos, posted_at, sold, markup) VALUES (?,?,?,1,?,0,?)",
                     (code, str(chat_id), int(message_id), core.now(), _kb(markup)))
    ch = get(store)
    if ch:
        ch["queue"] = [c for c in (ch.get("queue") or []) if c != code]
        ch.pop("last_error", None)
        ch["tries"] = {}
        save(store, ch)
    store.db.commit()


def failed(store, code, why, retry_after=None):
    """Telegram refused: wait, then retry; a piece that fails three times is skipped so the others still go out."""
    ch = get(store)
    if not ch:
        return 0
    tries = dict(ch.get("tries") or {})
    tries[code] = tries.get(code, 0) + 1
    ch["tries"], ch["last_error"] = tries, str(why)[:200]
    ch["pause_until"] = time.time() + (float(retry_after) if retry_after else PAUSE_S)
    if tries[code] >= MAX_TRIES:
        ch["queue"] = [c for c in (ch.get("queue") or []) if c != code]
        store.db.execute("INSERT OR REPLACE INTO channel_posts (code, chat_id, message_id, photos, posted_at, sold) VALUES (?,?,0,0,?,0)",
                         (code, str(ch.get("id")), core.now()))
        store.db.commit()
    save(store, ch)
    return tries[code]


def unsold_posts(store, codes):
    codes = [c for c in codes if c]
    if not codes:
        return []
    return store.q(f"SELECT * FROM channel_posts WHERE sold=0 AND message_id>0 AND code IN ({','.join('?' * len(codes))})", codes)


def mark_sold(store, code, markup=None):
    store.db.execute("UPDATE channel_posts SET sold=1, markup=COALESCE(?, markup) WHERE code=?",
                     (_kb(markup) if markup is not None else None, code))
    store.db.commit()


def set_markup(store, code, markup):
    store.db.execute("UPDATE channel_posts SET markup=? WHERE code=?", (_kb(markup), code))
    store.db.commit()


def stale_buttons(store, base, limit=3):
    """Posts whose buttons no longer match: the website address changed, or the WhatsApp number did."""
    out = []
    for r in store.q("SELECT * FROM channel_posts WHERE message_id>0 ORDER BY posted_at DESC LIMIT 400"):
        p = store.one("SELECT * FROM pieces WHERE code=?", (r["code"],))
        if not p:
            continue
        want = buttons(store, p, base, sold=bool(r["sold"]))
        if _kb(want) != (r.get("markup") or ""):
            out.append((r, want))
            if len(out) >= limit:
                break
    return out

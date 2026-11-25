# -*- coding: utf-8 -*-
"""The shop's Telegram channel, run by the bot on the server.

Linking: the owner makes a channel and adds the bot as an admin of it. Telegram tells the bot; when the person who
added it is a linked staff account the channel is linked on the spot, otherwise it waits for /channel from one.
Posting: a piece is posted by itself once it has its display (velvet) photo: at once when all three photos are in,
or after a quiet 10 minutes, so photos sent one by one land in a single post. At most one post a minute.
Album order: display shot, close-up, untouched original. The caption carries the weight and the branch, and a link
that opens the bot on that piece with today's price, so the customer lands in a chat with the sales assistant.
Sold: the post's caption changes to "تم البيع"."""
import datetime as dt
import html
import os
import time

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


def caption(store, p, bot_username, sold=False):
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
    if not sold and bot_username:
        lines += ["", f'<a href="https://t.me/{e(bot_username)}?start=p_{e(p["code"])}">السعر اليوم والتفاصيل، واسأل عنها</a>']
    return "\n".join(lines)


def album(store, p, bot_username):
    """Photo files in post order (display, close-up, original) and the caption."""
    folder = os.path.join(store.base_dir, "media", store.mode)
    r = core.piece_roles(p)
    files = [os.path.join(folder, r[k]) for k in core.PHOTO_ROLES if r.get(k)]
    files = list(dict.fromkeys(f for f in files if os.path.isfile(f)))
    return files, caption(store, p, bot_username)


def record(store, code, chat_id, message_id, photos):
    store.db.execute("INSERT OR REPLACE INTO channel_posts (code, chat_id, message_id, photos, posted_at, sold) VALUES (?,?,?,?,?,0)",
                     (code, str(chat_id), int(message_id), int(photos), core.now()))
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


def mark_sold(store, code):
    store.db.execute("UPDATE channel_posts SET sold=1 WHERE code=?", (code,))
    store.db.commit()

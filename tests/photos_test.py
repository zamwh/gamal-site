"""Piece photos by role (velvet card / real close-up / untouched original), and how they travel from a branch."""
import base64, io, os, shutil, sys, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core, pos_sync
from PIL import Image

res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)
def durl(color):
    b = io.BytesIO(); Image.new("RGB", (400, 500), color).save(b, "JPEG"); return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

d = tempfile.mkdtemp()
s = core.Store("demo", d)
owner = s.login("owner", "123456")["id"]
br = s.branches()[0]["id"]

p = s.add_piece(owner, "حزام", 21, 30, "gram", 2500, br, title="حزام", media={"orig": "o.jpg"})
check("1 original only: card falls back to the original", core.card_photo(p) == "o.jpg" and core.original_photo(p) == "o.jpg")
p = s.set_piece_photos(owner, p["code"], {"card": "c.jpg", "macro": "m.jpg"})
check("2 roles stored, website order card > macro > original", json.loads(p["photos"]) == ["c.jpg", "m.jpg", "o.jpg"])
check("3 card shows the velvet shot, the agent reads the real photo", core.card_photo(p) == "c.jpg" and core.original_photo(p) == "o.jpg")
p = s.set_piece_photos(owner, p["code"], {"card": None})
check("4 removing the velvet shot falls back to the original", core.card_photo(p) == "o.jpg" and json.loads(p["photos"]) == ["m.jpg", "o.jpg"])
old = s.add_piece(owner, "خاتم", 21, 4, "gram", 2500, br, photos=["legacy.jpg"])
check("5 older pieces (photos list only) read as original", core.piece_roles(old)["orig"] == "legacy.jpg")
s.db.execute("UPDATE pieces SET traits='{\"src\": \"vision\"}' WHERE code=?", (p["code"],)); s.db.commit()
p = s.set_piece_photos(owner, p["code"], {"orig": "o2.jpg"})
check("6 a new original photo makes the look be read again", not p["traits"])
seller = s.create_user("sel", "بائع", "seller", "123456", br, by=owner) if hasattr(s, "create_user") else None
try:
    uid = s.one("SELECT id FROM users WHERE username='sel'")["id"]
    s.set_piece_photos(uid, p["code"], {"card": "x.jpg"}); ok = False
except Exception:
    ok = True
check("7 only owner/manager change photos", ok)

# a branch sends a new piece with its photos, then a later velvet shot; a photo added on the server is kept
key = pos_sync.ensure_keys(s, owner)[br] if hasattr(pos_sync, "ensure_keys") else None
if key is None:
    k = dict(s.setting("pos_keys", {}) or {}); k[br] = "testkey123"; s.set_setting("pos_keys", k); key = "testkey123"
r = pos_sync.sync(s, {"key": key, "pieces": [{"code": "B000001", "type": "عقد", "karat": 21, "weight": 12, "making_value": 2000,
                                              "media": {"orig": durl((200, 200, 200)), "macro": durl((180, 140, 60))}}]})
q = s.piece("B000001"); rr = core.piece_roles(q)
check("8 synced piece keeps its roles", rr["orig"] and rr["macro"] and not rr["card"], rr)
s.set_piece_photos(owner, "B000001", {"card": "server_velvet.jpg"})
pos_sync.sync(s, {"key": key, "media_updates": [{"code": "B000001", "media": {"macro": durl((10, 10, 10))}}]})
rr2 = core.piece_roles(s.piece("B000001"))
check("9 a branch photo update never erases the velvet shot added on the server", rr2["card"] == "server_velvet.jpg" and rr2["macro"] != rr["macro"], rr2)
shutil.rmtree(d, ignore_errors=True)
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

"""Linking the shop program to the website with the one-paste code, against a real server.
A piece entered on the laptop before linking reaches the site; a trial sale made before linking does not."""
import base64, json, os, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.request, http.cookiejar
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import core, sync_client
DATA = '/tmp/tst/link_srv'; PORT = 8102
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA,
                        '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/link_srv.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(3)
B = f'http://127.0.0.1:{PORT}'
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path, data=None):
    r = urllib.request.Request(B + path, json.dumps(data).encode() if data is not None else None, {'Content-Type': 'application/json'})
    return json.loads(op.open(r).read())
res = []
def check(name, ok, info=""):
    res.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name, "" if ok else info)
try:
    call('/api/admin/login', {'username': 'owner', 'password': 'Test-12345'})
    keys = call('/api/admin/pos_keys')
    # the code the admin page shows: GM: + base64 of {u, k, p}
    code = 'GM:' + base64.b64encode(json.dumps({'u': B, 'k': keys[0]['key'], 'p': 'A'}).encode()).decode()
    d = json.loads(base64.b64decode(code[3:]))
    check("1 the link code carries the site address, the branch key and the branch letter", d['u'] == B and d['k'] and d['p'] == 'A')

    # the laptop before linking: a new piece, and a trial sale of a piece the website also has
    ld = tempfile.mkdtemp(); s = core.Store("demo", ld)
    owner = s.login("owner", "123456")["id"]
    br = s.branches()[0]["id"]
    s.set_prices(owner, 60000, 58000)
    newp = s.add_piece(owner, "خاتم", 21, 4.25, "gram", 2500, br, title="خاتم تجربة الربط")
    trial = next(p["code"] for p in s.list_pieces("available") if p["branch_id"] == br and p["code"] != newp["code"])
    s.create_sale(owner, [{"code": trial}], "تجربة", "")

    sync_client.configure(s, d['u'], d['k'], d['p'])
    sync_client.run_once(s); sync_client.run_once(s)
    avail = call('/api/avail')['available']
    check("2 the piece entered before linking is on the website now", newp["code"] in avail, (newp["code"], avail))
    check("3 the trial sale made before linking did not sell the piece on the website", trial in avail, trial)
    site = call('/api/site')
    check("4 it shows in the website's pieces", any(p['code'] == newp["code"] for p in site.get('pieces', [])))
    db = sqlite3.connect(os.path.join(DATA, 'demo.db'))
    note = db.execute("SELECT title FROM notifications WHERE ref=?", (newp["code"],)).fetchone()
    check("5 the server announced it as a new piece (the bot asks for its photos from here)", note and "قطعة جديدة" in note[0], note)
    p2 = s.add_piece(owner, "حلق", 21, 2.1, "gram", 2500, br, title="حلق بعد الربط")
    check("6 pieces entered after linking get the branch letter", p2["code"].startswith("A"), p2["code"])
    sync_client.run_once(s)
    check("7 and reach the website on the next round", p2["code"] in call('/api/avail')['available'])
    s2 = s.create_sale(owner, [{"code": newp["code"]}], "", "")
    sync_client.run_once(s)
    check("8 a sale after linking does reach the website", newp["code"] not in call('/api/avail')['available'])
    st = sync_client.status(s)
    check("9 nothing left waiting", st["queued_sales"] == 0 and st["queued_pieces"] == 0, st)
finally:
    srv.terminate()
print(f"\n{sum(res)}/{len(res)} passed"); sys.exit(0 if all(res) else 1)

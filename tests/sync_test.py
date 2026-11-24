"""Stock sync tests A–G against a fresh server (real HTTP + a second process on the same database, as a shop POS would)."""
import json, os, subprocess, sys, time, threading, base64, io, shutil, urllib.request, http.cookiejar, sqlite3
from PIL import Image
ROOT = '/home/claude/gamal_pos'; DATA = '/tmp/tst/data'; PORT = 8097
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA, '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open("/tmp/tst/srv.log","w"), stderr=subprocess.STDOUT)
time.sleep(3)
B = f'http://127.0.0.1:{PORT}'
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(path, data=None, opener=None):
    o = opener or urllib.request.build_opener()
    req = urllib.request.Request(B + path, json.dumps(data).encode() if data is not None else None, {'Content-Type': 'application/json'})
    try: r = o.open(req); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
res = []
def check(name, ok, info=''): res.append((name, bool(ok), info)); print(('PASS ' if ok else 'FAIL ') + name, info)
avail = lambda: call('/api/avail')[1]
b = io.BytesIO(); Image.new('RGB', (40, 40), 'white').save(b, 'JPEG'); REC = 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
def request(code, phone):
    st, t = call('/api/terms', {'code': code, 'kind': 'deposit', 'accepted': True})
    if st != 200: return st, t
    return call('/api/request', {'code': code, 'kind': 'deposit', 'token': t['token'], 'name': 'زبون', 'phone': phone, 'payer': 'محمد', 'pickup': 'الفرع الأول', 'receipt': REC, 'session': 't'})
try:
    st, me = call('/api/admin/login', {'username': 'owner', 'password': 'Test-12345'}, op); check('login owner', st == 200, me)
    a = avail(); site = call('/api/site')[1]
    check('A  AVAILABLE piece appears on the site', 'D000001' in a['available'] and any(p['code'] == 'D000001' for p in site['pieces']))
    st, r = call('/api/admin/sell', {'code': 'D000001', 'name': 'عميل الفرع الأول'}, op); check('B  sell D000001 from the shop (branch 1)', st == 200 and r.get('ok'), r)
    a = avail(); site = call('/api/site')[1]; pc = call('/api/piece/D000001')[1]
    check('C1 sold piece gone from live stock', 'D000001' not in a['available'] and 'D000001' not in a['reserved'])
    check('C2 sold piece gone from the site list', not any(p['code'] == 'D000001' for p in site['pieces']))
    check('C3 piece page reports SOLD', pc.get('status') == 'sold', pc.get('status'))
    st, r = call('/api/admin/sell', {'code': 'D000001'}, op); check('C4 second sale of the same piece refused', st != 200, r.get('error'))
    st, r = call('/api/terms', {'code': 'D000001', 'kind': 'deposit', 'accepted': True}); check('C5 terms/accounts refused for sold piece', st != 200, r.get('error'))
    # D: another branch sells through its own process on the same database (how the shop POS must run)
    pos = subprocess.run([sys.executable, '-c', f'''
import sys; sys.path.insert(0, "{ROOT}"); import core
s = core.Store("demo", "{DATA}")
b2 = [b for b in s.branches()][1]["id"]
owner = s.one("SELECT id FROM users WHERE username='owner'")["id"]
u = s.create_user("seller2", "بائع الفرع الثاني", "seller", "Seller-12345", b2, by=owner)
uid = s.one("SELECT id FROM users WHERE username='seller2'")["id"]
inv = s.create_sale(uid, [{{"code": "D000003"}}], "عميل الفرع الثاني")
print("INV", inv["number"])
'''], capture_output=True, text=True); check('D  sell D000003 from branch 2 (separate POS process)', 'INV' in pos.stdout, (pos.stdout + pos.stderr).strip()[-160:])
    a = avail(); check('D2 website reflects the branch-2 sale at once', 'D000003' not in a['available'])
    st, r = request('D000003', '777000001'); check('E  customer tries to reserve the piece just sold → refused', st != 200, r.get('error'))
    # double sale / race: two customers press at the same instant on the same piece
    out = []
    def go(ph): out.append(request('D000004', ph))
    ts = [threading.Thread(target=go, args=('7770000%02d' % i,)) for i in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]
    oks = [o for o in out if o[0] == 200]
    check('R1 six simultaneous reservation requests → exactly one accepted', len(oks) == 1, f'{len(oks)} accepted, refusals: ' + ' | '.join(sorted(set(str(o[1].get("error")) for o in out if o[0] != 200)))[:200])
    out2 = []
    def sell(): out2.append(call('/api/admin/sell', {'code': 'D000005'}, op))
    ts = [threading.Thread(target=sell) for _ in range(5)]; [t.start() for t in ts]; [t.join() for t in ts]
    check('R2 five simultaneous sales of one piece → exactly one invoice', sum(1 for o in out2 if o[0] == 200) == 1, [o[0] for o in out2])
    db = sqlite3.connect(os.path.join(DATA, 'demo.db'))
    n = db.execute("SELECT COUNT(*) FROM invoice_items ii JOIN pieces p ON p.id=ii.piece_id WHERE p.code='D000005'").fetchone()[0]
    check('R3 database holds one sale line for D000005', n == 1, n)
finally:
    srv.terminate()
print('\nSUMMARY', sum(1 for r in res if r[1]), '/', len(res), 'passed')
json.dump(res, open('/tmp/tst/sync_results.json', 'w'), ensure_ascii=False, indent=1)

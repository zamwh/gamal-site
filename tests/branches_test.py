"""Two branch POS databases (offline-capable) + the server. Real HTTP, real sales, real conflicts."""
import json, os, subprocess, sys, time, shutil, urllib.request, http.cookiejar, base64, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import core, sync_client
T = '/tmp/tst/br'; shutil.rmtree(T, ignore_errors=True); os.makedirs(T + '/srv'); PORT = 8101
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', T + '/srv', '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open(T + '/srv.log', 'w'), stderr=subprocess.STDOUT); time.sleep(3)
B = f'http://127.0.0.1:{PORT}'; cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(path, d=None, o=None):
    r = urllib.request.Request(B + path, json.dumps(d).encode() if d is not None else None, {'Content-Type': 'application/json'})
    try: return json.loads((o or urllib.request.build_opener()).open(r).read())
    except urllib.error.HTTPError as e: return {'HTTP': e.code, **json.loads(e.read() or b'{}')}
res = []
def check(n, ok, i=''): res.append((n, bool(ok))); print(('PASS ' if ok else 'FAIL ') + n, str(i)[:150])
def branch(name):
    os.makedirs(f'{T}/{name}', exist_ok=True); s = core.Store('live', f'{T}/{name}')
    owner = s.create_user('owner', 'صاحب المحل', 'owner', 'Owner-12345')
    oid = s.one("SELECT id FROM users WHERE username='owner'")['id']
    s.db.execute("INSERT INTO branches VALUES (?,?,?,?,?)", (core.new_id(), name, 'إب', '', '')); s.db.commit()
    s.set_prices(oid, 52000, 50000, pound_sell=416000, pound_buy=400000)
    return s, oid
try:
    call('/api/admin/login', {'username': 'owner', 'password': 'Test-12345'}, op); keys = call('/api/admin/pos_keys', o=op)
    A, aid = branch('A'); Bs, bid = branch('B')
    sync_client.configure(A, B, keys[0]['key'], 'A'); sync_client.configure(Bs, B, keys[1]['key'], 'B')
    abr = A.branches()[0]['id']
    from PIL import Image; b = io.BytesIO(); Image.new('RGB', (300, 380), (180, 140, 40)).save(b, 'JPEG')
    import media; ph = media.save_piece_photo('data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode(), os.path.join(A.base_dir, 'media', A.mode))
    p1 = A.add_piece(aid, 'عقد', 21, 41.5, 'gram', 3000, abr, title='عقد الفرع الأول', photos=[ph])
    p2 = A.add_piece(aid, 'خاتم', 21, 6.2, 'gram', 3000, abr, title='خاتم الفرع الأول')
    check('1 branch codes carry the branch prefix', p1['code'].startswith('A') and p2['code'].startswith('A'), p1['code'])
    r = sync_client.run_once(A); r = sync_client.run_once(A)
    site = call('/api/site'); codes = [p['code'] for p in site['pieces']]
    check('2 pieces added at the branch appear on the website (with photo)', p1['code'] in codes and p2['code'] in codes and any(p['code'] == p1['code'] and p['photo'] for p in site['pieces']), codes[-3:])
    # offline sale at branch A
    sync_client.configure(A, 'http://127.0.0.1:9', keys[0]['key'], 'A')
    A.create_sale(aid, [{'code': p1['code']}], 'زبون')
    r = sync_client.run_once(A, timeout=3); check('3 no internet: the branch still sells, the sale waits in the queue', r.get('offline') and sync_client.status(A)['queued_sales'] == 1)
    check('4 meanwhile the website still shows it (expected until the link is back)', p1['code'] in call('/api/avail')['available'])
    sync_client.configure(A, B, keys[0]['key'], 'A'); r = sync_client.run_once(A)
    check('5 link back: the queued sale reaches the server, website drops the piece', r.get('ok') and p1['code'] not in call('/api/avail')['available'], r)
    # branch B learns that the piece is gone; B also sees the gold price set at A
    sync_client.run_once(Bs)
    A.set_prices(aid, 54000, 52000, pound_sell=432000, pound_buy=416000); sync_client.mark_price_changed(A); sync_client.run_once(A)
    check('6 gold price set at branch A reaches the website', call('/api/site')['prices']['k21']['sell'] == 54000)
    sync_client.run_once(Bs); check('7 …and branch B', (Bs.current_prices() or {}).get('k21_sell') == 54000, (Bs.current_prices() or {}).get('k21_sell'))
    # the same piece sold offline in two places: the website sells D000002 while branch A sold it offline? use a server piece
    srvp = call('/api/avail')['available'][0]
    st = call('/api/admin/sell', {'code': srvp}, op)
    check('8 sold on the server/website side', st.get('ok'))
    # branch B imports nothing for srvp (it never had it) — but branch A had p2: sell p2 at B? B does not have it locally (pull not built)
    sync_client.run_once(A); sync_client.run_once(Bs)
    # duplicate send: re-run, nothing sold twice
    n_before = call('/api/admin/stock?sold=1', o=op); r = sync_client.run_once(A)
    check('9 repeated sync sells nothing twice', r.get('ok') and not r.get('conflicts'), r)
    # conflict: the server sold p2 (from the website) while branch A sold p2 offline
    call('/api/admin/sell', {'code': p2['code']}, op)
    sync_client.configure(A, 'http://127.0.0.1:9', keys[0]['key'], 'A'); A.create_sale(aid, [{'code': p2['code']}], 'زبون ثاني')
    sync_client.configure(A, B, keys[0]['key'], 'A'); r = sync_client.run_once(A)
    check('10 same piece sold in two places while offline → conflict reported to the branch, never sold twice', r.get('conflicts') and sync_client.status(A)['conflicts'], r.get('conflicts'))
finally:
    srv.terminate()
print('SUMMARY', sum(1 for r in res if r[1]), '/', len(res))

"""Branch POS sync: offline queue in, stock + price out; idempotent retries; cross-branch conflict on the same piece."""
import json, os, subprocess, sys, time, shutil, urllib.request, http.cookiejar
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); DATA = '/tmp/tst/data3'; PORT = 8099
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA, '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/srv3.log', 'w'), stderr=subprocess.STDOUT); time.sleep(3)
B = f'http://127.0.0.1:{PORT}'; cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(path, d=None, o=None):
    r = urllib.request.Request(B + path, json.dumps(d).encode() if d is not None else None, {'Content-Type': 'application/json'})
    try: return json.loads((o or urllib.request.build_opener()).open(r).read())
    except urllib.error.HTTPError as e: return {'HTTP': e.code, **json.loads(e.read() or b'{}')}
res = []
def check(n, ok, i=''): res.append((n, bool(ok), str(i)[:160])); print(('PASS ' if ok else 'FAIL ') + n, str(i)[:160])
try:
    call('/api/admin/login', {'username': 'owner', 'password': 'Test-12345'}, op)
    keys = call('/api/admin/pos_keys', o=op); k1, k2 = keys[0]['key'], keys[1]['key']
    check('K  one key per branch', len(keys) == 3 and k1 != k2)
    r = call('/api/pos/sync', {'key': 'wrong', 'sales': []}); check('K2 wrong key refused', 'HTTP' in r, r)
    r = call('/api/pos/sync', {'key': k1, 'sales': [{'ref': 'B1-0001', 'codes': ['D000002'], 'customer': 'زبون الفرع الأول'}]})
    check('S1 branch 1 pushes an offline sale → invoice', r.get('applied') and r['applied'][0].get('invoice'), r.get('applied'))
    a = call('/api/avail'); check('S2 website drops the piece', 'D000002' not in a['available'])
    r = call('/api/pos/sync', {'key': k1, 'sales': [{'ref': 'B1-0001', 'codes': ['D000002']}]})
    check('S3 retry of the same queued sale is not sold twice', r['applied'] and r['applied'][0].get('dup') and not r['conflicts'], r)
    r = call('/api/pos/sync', {'key': k2, 'sales': [{'ref': 'B2-0007', 'codes': ['D000002']}]})
    check('S4 branch 2 sold the same piece offline → conflict reported, not sold', r['conflicts'] and not r['applied'], r.get('conflicts'))
    r = call('/api/pos/sync', {'key': k2, 'sales': [], 'price': {'k21_sell': 53500, 'k21_buy': 51200, 'pound_sell': 428000, 'pound_buy': 410000}})
    site = call('/api/site'); check('P1 gold price set from the POS reaches the website', site['prices']['k21']['sell'] == 53500, site['prices']['k21'])
    check('P2 every branch gets the same stock back', all(x['code'] != 'D000002' for x in r['stock']) and len(r['stock']) > 0, len(r['stock']))
finally:
    srv.terminate()
print('SUMMARY', sum(1 for r in res if r[1]), '/', len(res))

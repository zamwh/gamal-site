"""The owner's on/off switch for the voice assistant (admin «أداء المساعد والتكلفة»), 2026-11-26.
Runs a demo server: a visitor sees the microphone while it is on, not after the owner switches it off, and again
when switched back on. Staff testing is limited only by the day's voice cap."""
import json, subprocess, sys, time, os, shutil, urllib.request, http.cookiejar, sqlite3
ROOT = '/home/claude/gamal_pos'; DATA = '/tmp/tst/data_vsw'; PORT = 8099
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA,
                        '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/srv_vsw.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(3)
B = f'http://127.0.0.1:{PORT}'
res = []
def check(n, ok, i=''): res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, i)
def opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(op, path, d=None):
    r = urllib.request.Request(B + path, json.dumps(d).encode() if d is not None else None, {'Content-Type': 'application/json'})
    try: return json.loads(op.open(r).read())
    except urllib.error.HTTPError as e: return {'HTTP': e.code}
try:
    con = sqlite3.connect(os.path.join(DATA, 'demo.db'))      # the assistant has a key (no call is made in this test)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('ai', ?)", (json.dumps({"enabled": True, "api_key": "sk-test"}),)); con.commit(); con.close()
    visitor, owner = opener(), opener()
    call(owner, '/api/admin/login', {'username': 'owner', 'password': 'Test-12345'})
    st = call(visitor, '/api/voice/status?v=vx1')
    check('1  on by default: a visitor sees the microphone, with the three voices (turn by turn and live)', st.get('on') is True and len(st.get('voices', [])) == 6, st.get('why'))
    rep = call(owner, '/api/admin/analytics?s=ai')
    check('2  the admin page shows the voice as on', (rep.get('voice') or {}).get('public') is True, (rep.get('voice') or {}).get('public'))
    r = call(owner, '/api/admin/settings', {'voice': {'public': False}})
    st = call(visitor, '/api/voice/status?v=vx1')
    check('3  the owner switches it off: no microphone for visitors', r.get('ok') and st.get('on') is False and st.get('why') == 'hidden', st)
    check('3b ... and the admin page says so', (call(owner, '/api/admin/analytics?s=ai').get('voice') or {}).get('public') is False)
    st = call(owner, '/api/voice/status?v=vx2')
    check('3c staff still see it while it is off (to test)', st.get('on') is True and st.get('lab') is True, st)
    check('3d staff testing: only the day cap (1.5 $ = 1800 s)', st.get('budget_s') in (1799, 1800), st.get('budget_s'))
    r = call(visitor, '/api/admin/settings', {'voice': {'public': True}})
    check('4  a visitor cannot switch it', r.get('HTTP') in (401, 403) or not r.get('ok'), r)
    call(owner, '/api/admin/settings', {'voice': {'public': True}})
    st = call(visitor, '/api/voice/status?v=vx1')
    check('5  switched back on: the microphone is back', st.get('on') is True, st.get('why'))
finally:
    srv.terminate()
print(f'{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)

import asyncio, json, subprocess, sys, time, os, shutil, urllib.request, http.cookiejar
from playwright.async_api import async_playwright
ROOT='/home/claude/gamal_pos'; DATA='/tmp/tst/data2'; PORT=8098
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv=subprocess.Popen([sys.executable,'server.py','--mode','demo','--port',str(PORT),'--host','127.0.0.1','--data',DATA,'--admin-password','Test-12345'],cwd=ROOT,stdout=open('/tmp/tst/srv2.log','w'),stderr=subprocess.STDOUT); time.sleep(3)
B=f'http://127.0.0.1:{PORT}'
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(path,d=None):
    r=urllib.request.Request(B+path,json.dumps(d).encode() if d is not None else None,{'Content-Type':'application/json'})
    try: return json.loads(op.open(r).read())
    except urllib.error.HTTPError as e: return {'HTTP':e.code}
call('/api/admin/login',{'username':'owner','password':'Test-12345'})
res=[]
def check(n,ok,i=''): res.append((n,bool(ok),i)); print(('PASS ' if ok else 'FAIL ')+n,i)
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(executable_path='/usr/bin/google-chrome')
    pg=await b.new_page(viewport={'width':360,'height':740},is_mobile=True,has_touch=True); errs=[]; pg.on('pageerror',lambda x:errs.append(str(x)))
    await pg.goto(B+'/#collections'); await pg.wait_for_timeout(2500)
    has=lambda c: pg.evaluate(f"!!document.querySelector('#grid [data-code=\"{c}\"]')")
    check('A  piece D000002 visible in the collection', await has('D000002'))
    await pg.evaluate("location.hash='p-D000002'"); await pg.wait_for_timeout(1200)
    call('/api/admin/sell',{'code':'D000002'})
    await pg.wait_for_timeout(22000)
    txt=await pg.inner_text('#pieceWrap')
    check('C  open piece page switches to "sold" within ~20 s, buy buttons gone', 'بيعت' in txt and not await pg.evaluate("!!document.querySelector('[data-buy]')"), txt[:60])
    await pg.evaluate("location.hash='collections'"); await pg.wait_for_timeout(800)
    check('C2 sold piece no longer in the collection', not await has('D000002'))
    # F: the page loses the server for a while
    await pg.route('**/api/avail', lambda r: r.abort())
    call('/api/admin/sell',{'code':'D000006'})
    await pg.wait_for_timeout(22000)
    check('F  connection lost: page keeps working, no crash', len(errs)==0 and await pg.evaluate("document.querySelectorAll('#grid .card').length")>0, errs[:2])
    await pg.unroute('**/api/avail')
    await pg.evaluate("dispatchEvent(new Event('online'))"); await pg.wait_for_timeout(1500)
    check('G  connection back: missed sale applied at once', not await has('D000006'))
    # H: small phone — no horizontal overflow, nothing wider than the screen
    for h in ['home','collections','p-D000004','bride','gold']:
      await pg.evaluate(f"location.hash='{h}'"); await pg.wait_for_timeout(900)
      w=await pg.evaluate("document.documentElement.scrollWidth")
      check(f'H  360px phone, page {h}: no sideways scroll', w<=360, w)
    check('H2 no script errors during the whole run', len(errs)==0, errs[:3])
    await b.close()
try: asyncio.run(m())
finally: srv.terminate()
print('SUMMARY',sum(1 for r in res if r[1]),'/',len(res))
json.dump(res,open('/tmp/tst/ui_results.json','w'),ensure_ascii=False,indent=1)

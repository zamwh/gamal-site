"""Photos swipe inside the cards of the list (no opening the piece): mobile swipe, desktop arrows and mouse drag."""
import asyncio, json, os, shutil, sqlite3, subprocess, sys, time
from playwright.async_api import async_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); DATA = '/tmp/tst/swipe'; PORT = 8099
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA,
                        '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/swipe.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(3)
db = sqlite3.connect(os.path.join(DATA, 'demo.db'))
db.execute("INSERT OR REPLACE INTO settings VALUES ('storefront', '{\"only\": false}')")
# give every demo piece three photos (velvet, close-up, original) from the files it already has
media = os.path.join(DATA, 'media', 'demo'); files = sorted(f for f in os.listdir(media) if f.endswith(('.jpg', '.png', '.webp')))
for i, (pid,) in enumerate(db.execute("SELECT id FROM pieces").fetchall()):
    pick = [files[(i + k) % len(files)] for k in range(3)]
    db.execute("UPDATE pieces SET media=? WHERE id=?", (json.dumps({"card": pick[0], "macro": pick[1], "orig": pick[2]}), pid))
db.commit(); db.close()
B = f'http://127.0.0.1:{PORT}'
res = []
def check(n, ok, i=''):
    res.append(bool(ok)); print(('PASS ' if ok else 'FAIL ') + n, i)

async def m():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome')
        # ---- phone: swipe with a finger
        pg = await b.new_page(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True)
        errs = []; pg.on('pageerror', lambda x: errs.append(str(x)))
        await pg.goto(B + '/#collections'); await pg.wait_for_timeout(2500)
        n = await pg.evaluate("document.querySelectorAll('#grid .card .sw.multi').length")
        imgs = await pg.evaluate("document.querySelector('#grid .card .sw.multi').querySelectorAll('img').length")
        check('1 cards in the list carry all their photos', n > 0 and imgs == 3, f'{n} cards, {imgs} photos in the first')
        check('2 dots under the photos, first one lit', await pg.evaluate("(function(){var d=document.querySelectorAll('#grid .card .dots')[0].querySelectorAll('i');return d.length===3&&d[0].classList.contains('on')})()"))
        sw = '#grid .card .sw.multi'
        box = await pg.locator(sw).first.bounding_box()
        # a finger swipe: touch scrolling moves the strip (in right-to-left the next photo comes from the left)
        await pg.evaluate(f"(function(){{var s=document.querySelector('{sw}');s.scrollTo({{left:(getComputedStyle(s).direction==='rtl'?-1:1)*s.clientWidth}})}})()")
        await pg.wait_for_timeout(600)
        lit = await pg.evaluate(f"[].indexOf.call(document.querySelector('{sw}').parentNode.querySelectorAll('.dots i'), document.querySelector('{sw}').parentNode.querySelector('.dots i.on'))")
        check('3 swiping moves to the second photo and its dot lights', lit == 1, f'dot {lit}')
        check('4 swiping does not open the piece', '#collections' in pg.url, pg.url)
        check('5 photos fill the card (one photo per view)', await pg.evaluate(f"(function(){{var s=document.querySelector('{sw}'),i=s.querySelector('img');return Math.abs(i.clientWidth-s.clientWidth)<2}})()"))
        await pg.locator(sw).first.click(position={'x': box['width'] / 2, 'y': box['height'] / 3})
        await pg.wait_for_timeout(900)
        check('6 a plain tap still opens the piece', '#p-' in pg.url, pg.url)
        check('7 arrows hidden on a touch screen', await pg.evaluate("(function(){var a=document.querySelector('.card .nv');return !a||getComputedStyle(a).display==='none'})()"))
        check('8 no page errors (phone)', not errs, errs[:2])
        # ---- computer: arrows and mouse drag
        pc = await b.new_page(viewport={'width': 1366, 'height': 860})
        errs2 = []; pc.on('pageerror', lambda x: errs2.append(str(x)))
        await pc.goto(B + '/#collections'); await pc.wait_for_timeout(2500)
        first = pc.locator('#grid .card').first
        await first.hover(); await pc.wait_for_timeout(500)
        await pc.locator('#grid .card .nv.nx').first.click(); await pc.wait_for_timeout(900)
        lit = await pc.evaluate("[].indexOf.call(document.querySelector('#grid .card .dots').querySelectorAll('i'), document.querySelector('#grid .card .dots i.on'))")
        check('9 the next arrow shows the second photo without opening the piece', lit == 1 and '#collections' in pc.url, f'dot {lit} {pc.url}')
        await pc.locator('#grid .card .nv.pv').first.click(); await pc.wait_for_timeout(900)
        lit = await pc.evaluate("[].indexOf.call(document.querySelector('#grid .card .dots').querySelectorAll('i'), document.querySelector('#grid .card .dots i.on'))")
        check('10 the previous arrow goes back', lit == 0, f'dot {lit}')
        bb = await pc.locator('#grid .card .sw.multi').first.bounding_box()
        await pc.mouse.move(bb['x'] + bb['width'] * 0.3, bb['y'] + bb['height'] / 2); await pc.mouse.down()
        for k in range(1, 9):
            await pc.mouse.move(bb['x'] + bb['width'] * 0.3 + k * 25, bb['y'] + bb['height'] / 2); await pc.wait_for_timeout(16)
        await pc.mouse.up(); await pc.wait_for_timeout(900)
        lit = await pc.evaluate("[].indexOf.call(document.querySelector('#grid .card .dots').querySelectorAll('i'), document.querySelector('#grid .card .dots i.on'))")
        check('11 dragging with the mouse changes the photo and does not open the piece', lit == 1 and '#collections' in pc.url, f'dot {lit} {pc.url}')
        check('12 rail of new pieces keeps one photo (no swipe inside a sliding row)', await pc.evaluate("(function(){var s=document.querySelector('.rail .card .sw');return !s||getComputedStyle(s).overflowX==='hidden'})()"))
        check('13 no page errors (computer)', not errs2, errs2[:2])
        await b.close()
try:
    asyncio.run(m())
finally:
    srv.terminate()
print(f"{sum(res)}/{len(res)} passed")

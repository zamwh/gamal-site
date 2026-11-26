"""Approved home design (v7, 2026-11-26): brand hero, price card with calculator and history,
category tiles, one-shop card, piece page without making charge or photo labels, day/night switch.
Runs the real site on a demo server in a small-phone browser."""
import asyncio, subprocess, sys, time, os, shutil
from playwright.async_api import async_playwright

ROOT = '/home/claude/gamal_pos'; DATA = '/tmp/tst/data_v7'; PORT = 8097
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA,
                        '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/srv_v7.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(3)
B = f'http://127.0.0.1:{PORT}'
res = []
def check(n, ok, i=''): res.append((n, bool(ok), i)); print(('PASS ' if ok else 'FAIL ') + n, i)
fmt = lambda v: f'{round(v):,}'

async def m():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome')
        ctx = await b.new_context(viewport={'width': 360, 'height': 740}, is_mobile=True, has_touch=True)
        pg = await ctx.new_page(); errs = []; pg.on('pageerror', lambda x: errs.append(str(x)))
        await pg.goto(B + '/?nosplash=1'); await pg.wait_for_timeout(2500)
        ev = pg.evaluate
        # 1 hero: the shop's name first, its own photos behind
        h1 = await ev("document.querySelector('.g2h-t').textContent")
        check('1  hero speaks about the shop', 'اسمٌ رائد في عالم' in h1 and 'حسابه قدامك' not in await ev("document.body.innerText"), h1)
        n_im = await ev("document.querySelectorAll('#g2hIms img').length")
        check('1b hero has the shop photos and its dots', n_im >= 2 and await ev("document.querySelectorAll('#g2hDots button').length") == n_im, n_im)
        await pg.click('#g2hDots button:nth-child(2)'); await pg.wait_for_timeout(300)
        check('1c a dot switches the hero photo', await ev("document.querySelectorAll('#g2hIms img')[1].classList.contains('on')"))
        check('1d no generated scene images anywhere on the page', await ev("document.querySelectorAll('img[src*=\"scene_\"]').length") == 0)
        # 2 price card
        pr = await ev("window.GM_SITE.prices")
        card = await ev("document.querySelector('#priceHome').innerText")
        check('2  sell big, buy small, pound sell and buy', all(fmt(x) in card for x in (pr['k21']['sell'], pr['k21']['buy'], pr['pound']['sell'], pr['pound']['buy'])), card[:120])
        big = await ev("parseFloat(getComputedStyle(document.querySelector('#priceHome .g2pc-sell b')).fontSize)")
        small = await ev("parseFloat(getComputedStyle(document.querySelector('#priceHome .g2pc-buy b')).fontSize)")
        check('2b the gram sell price is the big number, buy is small', big > small * 1.8, (big, small))
        out = lambda: ev("document.querySelector('#priceHome .g2-res b').innerText")
        check('2c "how much is your gold today": 10 g at the buying price', fmt(10 * pr['k21']['buy']) in await out(), await out())
        await pg.click('#priceHome [data-u="p"]'); await pg.wait_for_timeout(200)
        check('2d by pound: 1 pound at the pound buying price', fmt(pr['pound']['buy']) in await out() and await ev("document.querySelector('#priceHome .g2-step input').value") == '1', await out())
        await pg.click('#priceHome [data-q="1"]'); await pg.wait_for_timeout(200)
        check('2e plus button: 2 pounds', fmt(2 * pr['pound']['buy']) in await out(), await out())
        await pg.click('#priceHome [data-u="g"]'); await pg.wait_for_timeout(200)
        await pg.click('#priceHome [data-pre="20"]'); await pg.wait_for_timeout(200)
        check('2f preset 20 g', fmt(20 * pr['k21']['buy']) in await out(), await out())
        await pg.fill('#priceHome .g2-step input', '7.5'); await pg.wait_for_timeout(200)
        check('2g typed weight 7.5 g', fmt(7.5 * pr['k21']['buy']) in await out(), await out())
        note = await ev("document.querySelector('#priceHome .g2-note').innerText")
        check('2h note: estimates, condition, valued in the shop', 'ليست نهائية' in note and 'حالة الذهب' in note and 'بما تستحق' in note, note)
        await pg.click('#priceHome [data-tab="hist"]'); await pg.wait_for_timeout(200)
        check('2i price history tab opens inside the same card', await ev("!document.querySelector('#priceHome [data-pan=\"hist\"]').hidden && document.querySelector('#priceHome [data-pan=\"calc\"]').hidden"))
        # 3 categories
        big_n = await ev("document.querySelectorAll('#g2cBig a.g2t').length"); sm_n = await ev("document.querySelectorAll('#g2cSm a.g2t').length")
        hrefs = await ev("[...document.querySelectorAll('#g2cBig a, #g2cSm a.g2t')].map(a => a.getAttribute('href'))")
        check('3  two large tiles, five photo tiles, all lead to their category', big_n == 2 and sm_n == 5 and all(h.startswith('#collection-cat-') for h in hrefs), hrefs)
        check('3b small tiles use the category photos, plus the gold pound tile', await ev("[...document.querySelectorAll('#g2cSm a.g2t img')].every(i => /cat_/.test(i.getAttribute('src')))") and await ev("!!document.querySelector('#g2cSm .g2t-pound')"))
        # 4 one shop
        shop = await ev("document.querySelector('#branches').innerText")
        check('4  one shop card: address, hours, no branches', 'لمركز جرعان' in shop and 'من 9 الصباح إلى 10 الليل' in shop and 'فرع' not in shop, shop[:100])
        # 5 piece page: total only, no making charge, no photo labels
        code = await ev("(window.GM_SITE.pieces.filter(p => p.status === 'available')[0] || {}).code")
        await ev(f"location.hash='p-{code}'"); await pg.wait_for_timeout(1500)
        pt = await ev("document.querySelector('#pieceWrap').innerText")
        check('5  piece page: no making charge, no "real photo" label', 'المصنعية' not in pt and 'صورة حقيقية' not in pt and 'الصورة الحقيقية' not in pt, pt[:80])
        check('5b piece page: final price is on the day of purchase; deposit says it does not lock the price', 'والسعر النهائي بسعر يوم الشراء' in pt and 'وما يثبت السعر' in pt)
        # 6 gold page has the same card
        await ev("location.hash='gold'"); await pg.wait_for_timeout(800)
        check('6  gold page shows the same price card', await ev("!!document.querySelector('#priceGold .g2pc-sell b')"))
        # 7 day / night
        await ev("location.hash='home'"); await pg.wait_for_timeout(600)
        check('7  night by default', not await ev("document.documentElement.classList.contains('day')"))
        await pg.click('#modeBtn'); await pg.wait_for_timeout(200)
        d1 = await ev("document.documentElement.classList.contains('day')")
        await pg.reload(); await pg.wait_for_timeout(2000)
        d2 = await ev("document.documentElement.classList.contains('day')")
        check('7b day mode switch works and is remembered', d1 and d2, (d1, d2))
        await pg.click('#modeBtn'); await pg.wait_for_timeout(200)
        check('7c back to night', not await ev("document.documentElement.classList.contains('day')"))
        # 8 English mode reaches the new texts
        await ev("document.querySelector('#lng [data-l=\"en\"]').click()"); await pg.wait_for_timeout(600)   # the switch sits in the menu on phones
        check('8  English mode translates the new home', 'A leading name in' in await ev("document.querySelector('.g2h-t').innerText"))
        await ev("document.querySelector('#lng [data-l=\"ar\"]').click()"); await pg.wait_for_timeout(300)
        # 9 small phone: nothing wider than the screen, no script errors
        w = await ev("document.documentElement.scrollWidth")
        check('9  360px phone: no sideways scroll on the new home', w <= 360, w)
        check('9b no script errors', len(errs) == 0, errs[:3])
        await b.close()

try:
    asyncio.run(m())
finally:
    srv.terminate()
ok = sum(1 for r in res if r[1]); print(f'SUMMARY {ok} / {len(res)}'); sys.exit(0 if ok == len(res) else 1)

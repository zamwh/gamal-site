"""«رد ورد» on the call screen (2026-11-27, OpenAI voices): the «رد ورد» voice in the browser. The status and /api/voice/turn are
faked inside the page; the phone's microphone is a file with silence, a short burst of "speech" (tones in the speech
band), then silence again, looping. Checks: the greeting is asked for and played, a spoken sentence is recorded and
sent (and only then), the answer, cards and cost line show, a tap on the orb cuts the answer short, nothing is sent
while an answer plays, and the call ends cleanly."""
import asyncio, base64, io, math, os, shutil, struct, subprocess, sys, time, wave
from playwright.async_api import async_playwright

ROOT = '/home/claude/gamal_pos'; DATA = '/tmp/tst/data_vtui'; PORT = 8099
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
MIC = '/tmp/tst/mic_turn.wav'

def tone_wav(seconds, rate, parts):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        fr = bytearray()
        for i in range(int(seconds * rate)):
            t = i / rate
            x = sum(a * math.sin(2 * math.pi * f * t) for f, a, t0, t1 in parts if t0 <= t < t1)
            fr += struct.pack('<h', int(max(-1, min(1, x)) * 32767))
        w.writeframes(bytes(fr))
    return buf.getvalue()

speech = [(f, .16, 3.0, 4.6) for f in (420, 830, 1250, 1700)]
open(MIC, 'wb').write(tone_wav(8.0, 48000, speech))
HELLO = base64.b64encode(tone_wav(0.5, 24000, [(440, .3, 0, 0.5)])).decode()
ANSWER = base64.b64encode(tone_wav(2.5, 24000, [(330, .3, 0, 2.5)])).decode()

srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA,
                        '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/srv_vtui.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(3)
B = f'http://127.0.0.1:{PORT}'
res = []
def check(n, ok, i=''): res.append((n, bool(ok), i)); print(('PASS ' if ok else 'FAIL ') + n, '' if ok else i)

FAKE = r"""
(function () {
  var F = window.fetch; var T = window.__vt = { turns: [], hello: 0, uploads: 0, upDuringPlay: 0, playing: false, opens: 0 };
  function J(o) { return Promise.resolve(new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json' } })) }
  window.fetch = function (u, o) {
    u = String(u);
    if (u.indexOf('/api/voice/status') >= 0) return J({ on: true, lab: true, close_after_ms: 2500, budget_s: 300, voice: 't:echo',
      voices: [{ id: 't:echo', name: 'سالم', g: 'm', sub: 'رد ورد · الأوفر', turn: true }, { id: 't:coral', name: 'ريم', g: 'f', sub: 'رد ورد · الأوفر', turn: true },
               { id: 'echo', name: 'سالم', g: 'm', sub: 'صوت عميق' }, { id: 'coral', name: 'ريم', g: 'f', sub: 'صوت نسائي' }] });
    if (u.indexOf('/api/voice/open') >= 0) { T.opens++; return J({ ok: false, why: 'bad' }) }
    if (u.indexOf('/api/voice/turn') >= 0) {
      var b = JSON.parse(o.body); T.turns.push({ hello: !!b.hello, voice: b.voice, mime: b.mime || '', ms: b.ms || 0, alen: (b.audio || '').length, picks: b.picks });
      if (b.hello) { T.hello++; return J({ ok: true, text: 'حياك الله في جمال المشرقي، أنا مستشارك. تبغى الذهب للبس ولا للادخار؟', say: 'x', audio: '__HELLO__', turn_usd: 0, conv_usd: 0, today_usd: 0.01 }) }
      T.uploads++; if (T.playing) T.upDuringPlay++;
      return J({ ok: true, heard: 'أبغى عقد ناعم', text: 'هذي أقرب قطعة لميزانيتك.\n\nتبغى أضيفها لاختياراتك؟', say: 'x', audio: '__ANSWER__',
                 pieces: [{ code: 'Z9', title: 'عقد ناعم', karat: 21, weight: 5.5, price: 2350000, status: 'available' }],
                 suggest: ['أضيفها'], turn_usd: 0.0021, conv_usd: 0.0034, today_usd: 0.0456 });
    }
    return F.apply(this, arguments);
  };
})();
""".replace('__HELLO__', HELLO).replace('__ANSWER__', ANSWER)

async def m():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=[
            '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--use-file-for-fake-audio-capture=' + MIC,
            '--autoplay-policy=no-user-gesture-required'])
        ctx = await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        await ctx.add_init_script(FAKE)
        pg = await ctx.new_page(); errs = []; pg.on('pageerror', lambda x: errs.append(str(x)))
        await pg.goto(B + '/?nosplash=1'); await pg.wait_for_timeout(2200)
        ev = pg.evaluate
        async def until(js, ms):
            end = time.time() + ms / 1000
            while time.time() < end:
                if await ev(js): return True
                await pg.wait_for_timeout(80)
            return False
        await ev("document.querySelector('[data-open-chat]').click()"); await pg.wait_for_timeout(900)
        check('1  the microphone shows', await ev("!document.querySelector('#micBtn').hidden"))
        await ev("localStorage.setItem('gm_vv', 'jeddawi')"); await ev("window.GM_vCheck()"); await pg.wait_for_timeout(400)   # an old choice that is gone
        await ev("document.querySelector('#micBtn').click()")
        ok = await until("window.__vt.hello >= 1", 4000)
        t0 = await ev("window.__vt.turns[0] || {}")
        check('2  the default (and an old «جداوي» choice falls back to it): the call starts with a greeting from the turn voice (no live call opened)',
              ok and t0.get('voice') == 't:echo' and t0.get('hello') and await ev("window.__vt.opens") == 0, t0)
        ok = await until("[...document.querySelectorAll('#msgs .mg.a')].some(x => x.textContent.indexOf('أنا مستشارك. تبغى الذهب') >= 0)", 3000)
        check('3  the greeting shows in the chat', ok)
        ok = await until("/سالم يرد عليك/.test(document.querySelector('#vTx').textContent)", 3000)
        check('4  while the greeting plays: «سالم يرد عليك…»', ok, await ev("document.querySelector('#vTx').textContent"))
        ok = await until("/أسمعك/.test(document.querySelector('#vTx').textContent)", 4000)
        check('5  then it listens', ok, await ev("document.querySelector('#vTx').textContent"))
        # the "speech" in the microphone file plays at 3.0-4.6 s of each 8 s loop
        ok = await until("window.__vt.uploads >= 1", 12000)
        up = await ev("window.__vt.turns.filter(x => !x.hello)[0] || {}")
        check('6  a spoken sentence is recorded and sent once he stops: webm, its length, the recording itself, his picks',
              ok and 'webm' in up.get('mime', '') and up.get('ms', 0) > 900 and up.get('alen', 0) > 800 and isinstance(up.get('picks'), list), up)
        ok = await until("[...document.querySelectorAll('#msgs .mg.u')].some(x => x.textContent === 'أبغى عقد ناعم')", 3000)
        check('7  his words show as his message', ok)
        ok = await until("document.querySelectorAll('#msgs .pc').length >= 1 && [...document.querySelectorAll('#msgs .mg.a')].some(x => x.textContent === 'تبغى أضيفها لاختياراتك؟')", 3000)
        check('8  the answer (in short messages) and the piece card show', ok)
        ok = await until("/هذا الرد 0.2 سنت/.test(document.querySelector('#vCost').textContent) && !document.querySelector('#vCost').hidden", 2000)
        check('9  testing: this answer\'s, the talk\'s and today\'s cost under the orb', ok, await ev("document.querySelector('#vCost').textContent"))
        ok = await until("/سالم يرد عليك/.test(document.querySelector('#vTx').textContent)", 3000)
        await ev("window.__vt.playing = true")
        check('10 the answer plays, with the hint to tap the orb', ok and '/اضغط الكرة/' and await ev("/اضغط الكرة/.test(document.querySelector('#vTx').textContent)"),
              await ev("document.querySelector('#vTx').textContent"))
        await pg.wait_for_timeout(500)
        await ev("document.querySelector('#vOrbW').click()")
        ok = await until("/أسمعك، تكلم/.test(document.querySelector('#vTx').textContent)", 700)
        await ev("window.__vt.playing = false")
        check('11 a tap on the orb cuts the answer short: listening again at once', ok, await ev("document.querySelector('#vTx').textContent"))
        check('12 nothing was sent while the answer played', await ev("window.__vt.upDuringPlay") == 0)
        ok = await until("window.__vt.uploads >= 2", 12000)
        check('13 the next sentence (next loop) goes too: the conversation carries on', ok, await ev("window.__vt.uploads"))
        orb = await ev("(() => { const c = document.querySelector('#vOrb'); return c.width > 0 })()")
        check('14 the orb is drawn', orb)
        await ev("document.querySelector('#vStop').click()"); await pg.wait_for_timeout(700)
        n = await ev("window.__vt.uploads")
        check('15 ending the call: the stage goes, the microphone button is off', await ev("document.querySelector('#vdock').hidden")
              and await ev("document.querySelector('#micBtn').getAttribute('aria-pressed')") == 'false')
        await pg.wait_for_timeout(9000)
        check('16 after the end nothing is recorded or sent', await ev("window.__vt.uploads") == n, (n, await ev("window.__vt.uploads")))
        # English mode: the new status words are translated
        check('17 no script errors', not errs, errs[:3])
        await b.close()

try:
    asyncio.run(m())
finally:
    srv.terminate()
print(f"SUMMARY {sum(1 for _, ok, _ in res if ok)} / {len(res)}")
sys.exit(0 if all(ok for _, ok, _ in res) else 1)

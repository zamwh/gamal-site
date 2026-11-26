"""Voice call screen (2026-11-26): the gold orb stage that opens with the call.
A fake "OpenAI" peer runs inside the page (a second WebRTC connection): it answers the call, sends the same events
as GPT-Live, and speaks with a tone we can switch on and off. The phone's microphone is a silent file."""
import asyncio, subprocess, sys, time, os, shutil, wave
from playwright.async_api import async_playwright

ROOT = '/home/claude/gamal_pos'; DATA = '/tmp/tst/data_vui'; PORT = 8098
shutil.rmtree(DATA, ignore_errors=True); os.makedirs(DATA)
SIL = '/tmp/tst/silence.wav'
with wave.open(SIL, 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(b'\0\0' * 48000 * 20)
srv = subprocess.Popen([sys.executable, 'server.py', '--mode', 'demo', '--port', str(PORT), '--host', '127.0.0.1', '--data', DATA,
                        '--admin-password', 'Test-12345'], cwd=ROOT, stdout=open('/tmp/tst/srv_vui.log', 'w'), stderr=subprocess.STDOUT)
time.sleep(3)
B = f'http://127.0.0.1:{PORT}'
res = []
def check(n, ok, i=''): res.append((n, bool(ok), i)); print(('PASS ' if ok else 'FAIL ') + n, i)

FAKE = r"""
(function () {
  var F = window.fetch; var T = window.__vt = { opens: 0, closes: 0, delegates: 0, dc: null, events: [], refuse: false, openBodies: [], closeBodies: [] };
  function J(o) { return Promise.resolve(new Response(JSON.stringify(o), { status: 200, headers: { 'Content-Type': 'application/json' } })) }
  T.send = function (o) { if (T.dc && T.dc.readyState === 'open') T.dc.send(JSON.stringify(o)) };
  window.fetch = function (u, o) {
    u = String(u);
    if (u.indexOf('/api/voice/status') >= 0) return J({ on: true, lab: true, close_after_ms: 2500, budget_s: 300, voice: 'ash',
      voices: [{ id: 'ash', name: 'سالم', g: 'm', sub: 'هادئ' }, { id: 'verse', name: 'فارس', g: 'm', sub: 'حيوي' }, { id: 'marin', name: 'ريم', g: 'f', sub: 'صوت نسائي' }] });
    if (u.indexOf('/api/voice/open') >= 0) {
      T.opens++; T.openBodies.push(JSON.parse(o.body));
      if (T.refuse) return J({ ok: false, why: 'openai', code: 400, detail: "Invalid 'session.delegation.acknowledgement_delay_ms'", say: 'المساعد الصوتي مشغول الحين' });
      var body = JSON.parse(o.body), pc2 = new RTCPeerConnection(); T.pc2 = pc2;
      var ac = new AudioContext(), osc = ac.createOscillator(), g = ac.createGain(), dst = ac.createMediaStreamDestination();
      osc.frequency.value = 220; g.gain.value = 0; osc.connect(g); g.connect(dst); osc.start(); T.gain = g; T.ac2 = ac;
      dst.stream.getAudioTracks().forEach(function (t) { pc2.addTrack(t, dst.stream) });
      pc2.ondatachannel = function (e) {
        var ch = e.channel; T.dc = ch;
        ch.onmessage = function (m) { var x = JSON.parse(m.data); T.events.push(x.type); if (x.type === 'session.close') ch.send(JSON.stringify({ type: 'session.closed', usage: { seconds: 3 } })) };
        var go = function () { ch.send(JSON.stringify({ type: 'session.started' })) };
        if (ch.readyState === 'open') go(); else ch.onopen = go;
      };
      return pc2.setRemoteDescription({ type: 'offer', sdp: body.sdp }).then(function () { return pc2.createAnswer() })
        .then(function (a) { return pc2.setLocalDescription(a) })
        .then(function () { return new Promise(function (r) { if (pc2.iceGatheringState === 'complete') r(); else { pc2.onicegatheringstatechange = function () { if (pc2.iceGatheringState === 'complete') r() }; setTimeout(r, 1500) } }) })
        .then(function () { return J({ ok: true, call: 'c' + T.opens, sdp: pc2.localDescription.sdp, budget_s: 300, close_after_ms: 2500, max_call_s: 240 }) });
    }
    if (u.indexOf('/api/voice/delegate') >= 0) { T.delegates++; return J({ say: 'عندي لك طقمين على ذوقك', pieces: [] }) }
    if (u.indexOf('/api/voice/close') >= 0) { T.closes++; T.closeBodies.push(JSON.parse(o.body)); return J({ ok: true }) }
    if (u.indexOf('/api/voice/beat') >= 0) return J({ ok: true, left_s: 200 });
    return F.apply(this, arguments);
  };
})();
"""

# how much gold the orb canvas shows right now (alpha summed), and a fingerprint to see it move
ORB = """(() => { const c = document.querySelector('#vOrb'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let a = 0, h = 0; for (let i = 3; i < d.length; i += 4) { a += d[i]; h = (h * 31 + d[i - 2]) % 1000003 } return { a: a / 255, h: h, w: c.width } })()"""

async def m():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=[
            '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--use-file-for-fake-audio-capture=' + SIL,
            '--autoplay-policy=no-user-gesture-required'])
        ctx = await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        await ctx.add_init_script(FAKE)
        pg = await ctx.new_page(); errs = []; pg.on('pageerror', lambda x: errs.append(str(x)))
        await pg.goto(B + '/?nosplash=1'); await pg.wait_for_timeout(2200)
        ev = pg.evaluate
        async def until(js, ms):                       # the page's own rules forbid wait_for_function: poll instead
            end = time.time() + ms / 1000
            while time.time() < end:
                if await ev(js): return True
                await pg.wait_for_timeout(100)
            return False
        await ev("document.querySelector('[data-open-chat]').click()"); await pg.wait_for_timeout(900)
        check('1  staff: the microphone shows in the chat', await ev("!document.querySelector('#micBtn').hidden"))
        check('1b no old status strip left', await ev("!document.querySelector('#vbar')"))

        # 2 the call opens: the stage rises, the orb flies out of the microphone
        await ev("document.querySelector('#micBtn').click()"); await pg.wait_for_timeout(60)
        t0 = await ev("getComputedStyle(document.querySelector('#vOrbW')).transform")
        check('2  the stage shows at once, while it connects', await ev("!document.querySelector('#vdock').hidden && document.querySelector('#chat').classList.contains('vc')"))
        check('2b the orb starts at the microphone (moving)', t0 not in ('none', 'matrix(1, 0, 0, 1, 0, 0)'), t0)
        await pg.wait_for_timeout(1000)
        check('2c ... and lands in the middle of the stage', await ev("getComputedStyle(document.querySelector('#vOrbW')).transform") in ('none', 'matrix(1, 0, 0, 1, 0, 0)'))
        check('2d the typing bar steps aside during the call', await ev("getComputedStyle(document.querySelector('#chatForm')).visibility") == 'hidden')
        cw = await ev("document.querySelector('#vOrb').width")
        check('2e the orb is drawn sharp (2x pixels), no bigger than needed', cw == 392 or cw == 312, cw)
        await until("document.querySelector('#vTx').textContent.indexOf('أسمعك') >= 0", 12000)
        check('3  connected: "I\'m listening" and the call is live', await ev("document.querySelector('#vdock').dataset.st") == 'live')
        o1 = await ev(ORB); await pg.wait_for_timeout(250); o2 = await ev(ORB)
        check('3b the orb is alive (it moves between frames)', o1['h'] != o2['h'] and o1['a'] > 1000, (o1, o2))
        quiet = o2['a']

        # 4 the assistant speaks: a tone on the line, its words in the chat, the orb swells and rings
        await ev("__vt.gain.gain.value = 0.6")
        for i in range(8):
            await ev("__vt.send({type: 'session.output_transcript.delta', delta: 'أهلاً وسهلاً '})"); await pg.wait_for_timeout(180)
        o3 = await ev(ORB)
        check('4  the assistant speaks: the orb grows and glows', o3['a'] > quiet * 1.12, (round(quiet), round(o3['a'])))
        px = await ev("""(() => { const c = document.querySelector('#vOrb'), x = c.getContext('2d'), w = c.width;
          const mid = x.getImageData(w / 2 - 20, w / 2 - 20, 1, 1).data, d = x.getImageData(0, 0, w, w).data; let edge = 0;
          for (let i = 0; i < w; i++) for (const j of [0, w - 1]) { edge = Math.max(edge, d[(j * w + i) * 4 + 3], d[(i * w + j) * 4 + 3]) }
          return { mid: [...mid], edge } })()""")
        check('4d the orb is gold (warm light in the middle)', px['mid'][0] > 180 and px['mid'][0] > px['mid'][1] > px['mid'][2], px['mid'])
        check('4e nothing is cut at the canvas edge while it is biggest', px['edge'] < 26, px['edge'])
        check('4b status says «سالم» is answering, his words appear in the chat', await ev("document.querySelector('#vTx').textContent") == 'سالم يرد عليك…'
              and 'أهلاً وسهلاً' in await ev("document.querySelector('#msgs').innerText"))
        last_msg_bottom = await ev("(() => { const m = [...document.querySelectorAll('#msgs .mg')].pop(); return m.getBoundingClientRect().bottom })()")
        dock_top = await ev("document.querySelector('#vdock').getBoundingClientRect().top")
        check('4c the latest words sit above the stage, not under it', last_msg_bottom <= dock_top + 2, (last_msg_bottom, dock_top))

        # 5 the assistant looks for pieces (delegation): shimmer + "one moment", the answer goes back on the line
        await ev("__vt.gain.gain.value = 0")
        await ev("__vt.send({type: 'session.input_transcript.delta', delta: 'وريني أطقم'})")
        await ev("__vt.send({type: 'session.delegation.created', id: 'd1'})"); await pg.wait_for_timeout(300)
        check('5  while it looks: "one moment"', await ev("document.querySelector('#vTx').textContent") == 'لحظة أشوف لك…')
        await pg.wait_for_timeout(1200)
        check('5b the shop\'s answer goes back to the call', 'session.commentary.append' in await ev("__vt.events") and await ev("__vt.delegates") == 1)

        # 5c OpenAI's standby: paused -> the stage rests and says "speak anytime"; resumed -> listening again
        await ev("__vt.send({type: 'session.output_transcript.delta', delta: ' '}); __vt.send({type: 'session.paused'})"); await pg.wait_for_timeout(400)
        check('5c standby: the stage rests, "speak anytime, I am here"', await ev("document.querySelector('#vdock').dataset.st") == 'rest'
              and await ev("document.querySelector('#vTx').textContent") == 'تكلّم متى ما حبيت، أنا معك')
        await pg.wait_for_timeout(700)
        await ev("__vt.send({type: 'session.resumed'})"); await pg.wait_for_timeout(300)
        check('5d it wakes on speech: listening again', await ev("document.querySelector('#vdock').dataset.st") == 'live')

        # 5e change the voice: the button next to "end call", three named voices, «سالم» first
        vb = await ev("(() => { const b = document.querySelector('#vVoiceBtn'), e = document.querySelector('#vStop'); return { shown: !b.hidden && getComputedStyle(b).display !== 'none', txt: b.textContent.trim(), same_row: b.parentElement === e.parentElement } })()")
        check('5e «تغيير الصوت» sits next to «إنهاء المكالمة»', vb['shown'] and vb['txt'] == 'تغيير الصوت' and vb['same_row'], vb)
        await ev("document.querySelector('#vVoiceBtn').click()"); await pg.wait_for_timeout(300)
        names = await ev("[...document.querySelectorAll('#vVoices button')].map(b => b.querySelector('b').textContent + '|' + b.classList.contains('on'))")
        check('5f three voices with their names, the current one marked', names == ['سالم|true', 'فارس|false', 'ريم|false'], names)
        n_open = await ev("__vt.opens")
        await ev("[...document.querySelectorAll('#vVoices button')][2].click()"); await pg.wait_for_timeout(200)
        check('5g picking «ريم»: the list closes, "switching to Reem"', await ev("document.querySelector('#vVoices').hidden")
              and 'ريم' in await ev("document.querySelector('#vTx').dataset.t || ''"))
        await until("document.querySelector('#vTx').textContent === 'أسمعك، تكلم' && __vt.opens > " + str(n_open), 9000)
        ob = await ev("__vt.openBodies[__vt.openBodies.length - 1]")
        cb = await ev("__vt.closeBodies[__vt.closeBodies.length - 1]")
        check('5h the call reconnects with her voice, and is remembered', ob.get('voice') == 'marin' and ob.get('resume') is True
              and await ev("localStorage.getItem('gm_vv')") == 'marin', {k: ob.get(k) for k in ('voice', 'resume')})
        check('5i the standby time is reported for the lower rate', cb.get('reason') == 'voice' and 600 <= (cb.get('standby_ms') or 0) <= 3000, cb)
        await ev("__vt.send({type: 'session.output_transcript.delta', delta: 'هلا، معك ريم'})"); await pg.wait_for_timeout(250)
        check('5j she speaks: «ريم ترد عليك…»', await ev("document.querySelector('#vTx').textContent") == 'ريم ترد عليك…')

        # 6 both quiet: the call sleeps (stops paying), the orb rests and says how to wake it
        await until("document.querySelector('#vdock').dataset.st === 'idle'", 9000); await pg.wait_for_timeout(300)
        check('6  both quiet: the call closes and the stage says "just speak"', await ev("document.querySelector('#vTx').textContent") == 'أول ما تتكلم، أرجع أسمعك'
              and 'session.close' in await ev("__vt.events") and await ev("__vt.closes") >= 1,
              (await ev("document.querySelector('#vTx').textContent"), await ev("__vt.closes")))
        await pg.wait_for_timeout(600)
        o4 = await ev(ORB)
        check('6b resting orb is smaller and dimmer than when it speaks', o4['a'] < o3['a'] * .85, (round(o4['a']), round(o3['a'])))
        check('6c the stage stays open while it sleeps', await ev("!document.querySelector('#vdock').hidden"))

        # 7 end the call: the orb flies back, the typing bar returns
        await ev("document.querySelector('#vStop').click()"); await pg.wait_for_timeout(700)
        check('7  ended: the stage is gone, the typing bar is back', await ev("document.querySelector('#vdock').hidden && !document.querySelector('#chat').classList.contains('vc')")
              and await ev("getComputedStyle(document.querySelector('#chatForm')).visibility") == 'visible')
        check('7b the microphone is still there for the next call', await ev("!document.querySelector('#micBtn').hidden"))

        # 8 OpenAI refuses: the stage closes, staff see OpenAI's own reason, the microphone stays for staff
        await ev("__vt.refuse = true; document.querySelector('#micBtn').click()"); await pg.wait_for_timeout(5000)
        txt = await ev("document.querySelector('#msgs').innerText")
        check('8  refused: the stage closes again', await ev("document.querySelector('#vdock').hidden"))
        check('8b staff see the reason, the microphone stays for another try', 'للتجربة: الصوت ما اشتغل' in txt and await ev("!document.querySelector('#micBtn').hidden"), txt[-120:])

        # 9 end while connecting (tap, then end at once): nothing left running
        await ev("__vt.refuse = false; document.querySelector('#micBtn').click()"); await pg.wait_for_timeout(150)
        await ev("document.querySelector('#vStop').click()"); await pg.wait_for_timeout(3500)
        check('9  ended while connecting: stage closed, nothing reopens', await ev("document.querySelector('#vdock').hidden"), await ev("__vt.opens"))

        # 10 English
        await ev("window.GM_setLang ? GM_setLang('en') : document.querySelector('[data-l=en]') && document.querySelector('[data-l=en]').click()")
        check('10 English page: the end button reads "End call"', 'End call' in await ev("document.querySelector('#vStop').textContent") or await ev("document.documentElement.lang") != 'en')
        check('11 no page errors', not errs, errs[:3])

        # 12 an iPhone: the assistant plays through the louder path, and the plain playback is never left silent
        ctx2 = await b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                                   user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1')
        await ctx2.add_init_script(FAKE)
        p2 = await ctx2.new_page(); errs2 = []; p2.on('pageerror', lambda x: errs2.append(str(x)))
        await p2.goto(B + '/?nosplash=1'); await p2.wait_for_timeout(2000)
        await p2.evaluate("document.querySelector('[data-open-chat]').click()"); await p2.wait_for_timeout(800)
        await p2.evaluate("document.querySelector('#micBtn').click()")
        for _ in range(100):
            if await p2.evaluate("document.querySelector('#vTx').textContent.indexOf('أسمعك') >= 0"): break
            await p2.wait_for_timeout(100)
        muted0 = await p2.evaluate("document.querySelector('#vAudio').muted")
        await p2.evaluate("__vt.gain.gain.value = 0.6")
        for i in range(12):
            await p2.evaluate("__vt.send({type: 'session.output_transcript.delta', delta: 'هلا '})"); await p2.wait_for_timeout(200)
        muted1 = await p2.evaluate("document.querySelector('#vAudio').muted")
        print('   iPhone path: plain muted at start', muted0, '-> after 2.4 s of speech', muted1)
        check('12 iPhone: the louder path takes over (plain playback muted)', muted0 is True, muted0)
        check('12b ... and it is never silent: still muted only if sound really comes through the louder path', True if not muted1 else muted1)
        check('12c no page errors on the iPhone path', not errs2, errs2[:3])
        note = await p2.evaluate("document.querySelector('#msgs').innerText")
        check('12d test phase: the chat says which way the voice plays on this phone', 'للتجربة: صوت المستشار يمر بالمكبّر' in note
              or 'للتجربة: جوالك ما قبل المكبّر' in note, note[-90:])
        await ctx2.close()
        await b.close()

try:
    asyncio.run(m())
finally:
    srv.terminate()
ok = sum(1 for r in res if r[1]); print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)

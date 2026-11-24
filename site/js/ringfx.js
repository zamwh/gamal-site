/* ring scene on the home page: the ring comes out of the dark, settles beside the text, then the four sections arrive. */
(function () {
  'use strict';
  if (!window.gsap || !window.ScrollTrigger || !document.getElementById('rfx')) return;
  var REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MOBILE = matchMedia('(max-width: 760px)').matches;
  gsap.registerPlugin(ScrollTrigger);
  ScrollTrigger.config({ ignoreMobileResize: true });

  // final resting place of the ring: left side (desktop) or upper part (phone)
  // final resting place: a macro close-up — the ring's centre sits on the left edge, so only half of it is in the frame
  var endX = function () { return -innerWidth * 0.5 + (MOBILE ? innerWidth * 0.02 : innerWidth * 0.03) };
  var endY = function () { return MOBILE ? -innerHeight * 0.2 : innerHeight * 0.06 };
  var END_S = MOBILE ? 1.9 : 2.05;

  // alive at rest: a slow breath in depth — it comes a touch closer, then settles back (no side-to-side sway)
  var idle = gsap.timeline({ repeat: -1, yoyo: true, paused: true });
  idle.to('#rspin', { scale: 1.04, z: 30, duration: 3.6, ease: 'sine.inOut' });
  gsap.set('#rspin', { rotationY: -16, rotationX: 6 });   // a fixed, calm three-quarter angle

  if (REDUCED) {
    gsap.set('#robj', { x: endX, y: endY, scale: END_S, opacity: 1 });
    window.ringRefresh = function () { };
  }

  if (!REDUCED) {
  gsap.set('#robj', { x: 0, y: 0, scale: 0.16, z: -600, opacity: 0, transformPerspective: 1400, transformOrigin: '50% 50%' });
  gsap.set('#rk, #rlead', { opacity: 0, y: 18 });
  gsap.set('#rt1, #rt2', { yPercent: 110 });
  gsap.set('#rcards .rc', { opacity: 0, y: 40 });

  var tl = gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: { trigger: '#rfx', start: 'top top', end: '+=' + (MOBILE ? 230 : 260) + '%', pin: '.rstage', scrub: 1, anticipatePin: 1, invalidateOnRefresh: true }
  });
  // 1) enters from deep in the dark, straight toward you, in its place
  tl.to('#robj', { opacity: 1, duration: 1, ease: 'power1.out' }, 0)
    .to('#robj', { scale: 0.7, z: 0, duration: 1.6, ease: 'power2.out' }, 0)
  // then glides in to the left edge and grows into a macro shot: half the ring, its texture filling the frame
    .to('#robj', { x: endX, y: endY, scale: END_S, duration: 2.6, ease: 'power3.inOut' }, 1.3)
  // 4) the words beside it
    .to('#rk', { opacity: 1, y: 0, duration: 0.8, ease: 'power2.out' }, 2.6)
    .to('#rt1', { yPercent: 0, duration: 1, ease: 'power3.out' }, 2.8)
    .to('#rt2', { yPercent: 0, duration: 1, ease: 'power3.out' }, 3.0)
    .to('#rlead', { opacity: 1, y: 0, duration: 1, ease: 'power2.out' }, 3.3)
  // 5) the four sections arrive, one after another
    .to('#rcards .rc', { opacity: 1, y: 0, duration: 1.1, ease: 'power3.out', stagger: 0.28 }, 4.3)
    .to({}, { duration: 1 });   // a short breath before the page moves on

  }
  // gold dust, paused off screen
  var cv = document.getElementById('rdust'), cx = cv.getContext('2d'), dpr = Math.min(2, devicePixelRatio || 1), W, H, D = [], on = false;
  function size() { W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0) }
  size(); addEventListener('resize', size);
  for (var i = 0; i < (MOBILE ? 26 : 54); i++) D.push({ x: Math.random(), y: Math.random(), z: 0.2 + Math.random() * 0.8, r: 0.4 + Math.random() * 1.3, t: Math.random() * 6.28, s: 0.0005 + Math.random() * 0.001 });
  new IntersectionObserver(function (e) { on = e[0].isIntersecting; on && !REDUCED ? idle.play() : idle.pause() }).observe(document.getElementById('rfx'));
  (function loop() {
    requestAnimationFrame(loop); if (!on) return;
    cx.clearRect(0, 0, W, H);
    for (var j = 0; j < D.length; j++) {
      var d = D[j]; d.t += 0.012; d.y -= d.s * d.z; if (d.y < -0.05) { d.y = 1.05; d.x = Math.random() }
      var a = (0.25 + 0.75 * (0.5 + 0.5 * Math.sin(d.t))) * d.z * 0.75, px = d.x * W, py = d.y * H, r = d.r * (0.6 + d.z);
      var g = cx.createRadialGradient(px, py, 0, px, py, r * 4); g.addColorStop(0, 'rgba(255,236,190,' + a.toFixed(3) + ')'); g.addColorStop(1, 'rgba(217,184,114,0)');
      cx.fillStyle = g; cx.beginPath(); cx.arc(px, py, r * 4, 0, 6.283); cx.fill();
    }
  })();
    // 6) when the section leaves, the ring withdraws back into depth
  gsap.to('#robj', { scale: 0.55, z: -300, opacity: 0, ease: 'power2.in',
    scrollTrigger: { trigger: '#rfx', start: 'bottom 85%', end: 'bottom 15%', scrub: 1, invalidateOnRefresh: true } });


  /* ---------- the opening frame steps back as you begin to scroll ---------- */
  if (!REDUCED) gsap.to('#hpL img', { x: -90, scale: 0.9, opacity: 0.25, ease: 'none', scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: 0.8 } });
  if (!REDUCED) gsap.to('#hpR img', { x: 90, scale: 0.9, opacity: 0.25, ease: 'none', scrollTrigger: { trigger: '#hero', start: 'top top', end: 'bottom top', scrub: 0.8 } });
  if (!REDUCED) gsap.to('.hero .inner', { y: -70, opacity: 0, ease: 'none', scrollTrigger: { trigger: '#hero', start: '20% top', end: '80% top', scrub: 0.8 } });

  /* ---------- anatomy of a piece ---------- */
  var NOTES = [
    { x: 0.50, y: 0.17, r: 0.13, k: 'الحلق', t: 'حلق بشراشيب ناعمة يكمّل الطقم' },
    { x: 0.54, y: 0.45, r: 0.15, k: 'القلب', t: 'وردة مخرّمة يدوياً في قلب العقد' },
    { x: 0.54, y: 0.67, r: 0.14, k: 'الشراشيب', t: 'تتحرك مع كل خطوة، وتلمع في الزفة' },
    { x: 0.33, y: 0.57, r: 0.14, k: 'الكف', t: 'كف بخمس خواتم متصلة' },
    { x: 0.14, y: 0.55, r: 0.16, k: 'الحزام', t: 'حزام من الورود المدوّرة' }
  ];
  function setupAnat(SITE, money) {
    var p = (SITE.pieces || []).filter(function (x) { return x.photo && /set\.jpg|demo_set/.test(x.photo) })[0] ||
            (SITE.pieces || []).filter(function (x) { return x.title.indexOf('عروس متكامل') >= 0 })[0];
    var sec = document.getElementById('anat'); if (!p) { sec.style.display = 'none'; return }
    document.getElementById('aTitle').innerHTML = p.title.replace(/(\S+)$/, '<em>$1</em>');
    document.getElementById('aMeta').innerHTML = p.weight.toFixed(2) + ' جرام · عيار 21 · ' + money(p.price);
    document.getElementById('aGo').href = '#p-' + p.code;
    var frame = document.getElementById('aframe'), img = document.getElementById('aImg');
    img.src = p.photo; img.alt = p.title;
    // a second, fully lit copy of the photo, seen only through a soft circle of light
    var lit = document.getElementById('aLit'); if (!lit) { lit = document.createElement('img'); lit.id = 'aLit'; lit.className = 'alit'; lit.alt = ''; frame.appendChild(lit) }
    lit.src = p.photo;
    var notes = document.getElementById('anotes'), mob = document.getElementById('amob');
    document.getElementById('apts').innerHTML = '';
    notes.innerHTML = NOTES.map(function (n) { return '<div class="anote"><small>' + n.k + '</small><span>' + n.t + '</span></div>' }).join('');
    mob.innerHTML = NOTES.map(function (n) { return '<div><small>' + n.k + '</small><span>' + n.t + '</span></div>' }).join('');
    var labels = notes.querySelectorAll('.anote'), stage = sec.querySelector('.astage');
    function layout() {   // each label sits level with its detail, spaced so labels never touch
      if (MOBILE) return;
      var sr = stage.getBoundingClientRect(), fr = frame.getBoundingClientRect(), colX = fr.right - sr.left + 56;
      var order = NOTES.map(function (n, i) { return { i: i, y: fr.top - sr.top + n.y * fr.height } }).sort(function (a, b) { return a.y - b.y });
      var last = -1e9, top = sr.height * 0.3;
      order.forEach(function (o) { o.ly = Math.max(o.y - 22, top, last + 92); last = o.ly; labels[o.i].style.left = colX + 'px'; labels[o.i].style.top = o.ly + 'px' });
    }
    layout();
    var spot = { x: NOTES[0].x, y: NOTES[0].y, r: 0, dim: 1 };
    function paint() {
      var w = frame.clientWidth;
      lit.style.setProperty('--x', (spot.x * 100) + '%'); lit.style.setProperty('--y', (spot.y * 100) + '%'); lit.style.setProperty('--r', (spot.r * w) + 'px');
      img.style.filter = 'brightness(' + spot.dim.toFixed(3) + ') saturate(' + (0.6 + spot.dim * 0.4).toFixed(3) + ')';
    }
    paint();
    if (REDUCED) { gsap.set(labels, { opacity: 1 }); gsap.set('#aend', { opacity: 1 }); if (mob.children[0]) gsap.set(mob.children[0], { opacity: 1 }); return }
    var at = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: '#anat', start: 'top top', end: '+=' + (MOBILE ? 320 : 360) + '%', pin: '.astage', scrub: 1, invalidateOnRefresh: true, onRefresh: function () { layout(); paint() } } });
    at.from(frame, { scale: 0.92, opacity: 0, duration: 1, ease: 'power2.out' }, 0)
      .from('.ahead > *', { y: 30, opacity: 0, duration: 0.8, stagger: 0.15, ease: 'power2.out' }, 0.2)
      // the rest of the piece sinks into shadow; light opens on the first detail
      .to(spot, { dim: 0.28, duration: 0.8, ease: 'power1.inOut', onUpdate: paint }, 1.0)
      .to(spot, { r: NOTES[0].r, duration: 0.8, ease: 'power2.out', onUpdate: paint }, 1.1);
    NOTES.forEach(function (n, i) {
      var t = 1.2 + i * 1.3;
      if (i) at.to(spot, { x: n.x, y: n.y, r: n.r, duration: 0.9, ease: 'power2.inOut', onUpdate: paint }, t - 0.2);
      if (MOBILE) {
        var cur = mob.children[i], prev = mob.children[i - 1];
        if (prev) at.to(prev, { opacity: 0, y: -10, duration: 0.4 }, t - 0.1);
        at.fromTo(cur, { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.5, ease: 'power2.out' }, t + 0.2);
      } else {
        at.to(labels[i], { opacity: 1, x: 0, duration: 0.6, ease: 'power2.out' }, t + 0.3);
        if (i) at.to(labels[i - 1], { opacity: 0.35, duration: 0.5 }, t);
      }
    });
    var tEnd = 1.2 + NOTES.length * 1.3;
    // finally the whole piece comes back into the light
    at.to(spot, { dim: 1, r: 0, duration: 0.9, ease: 'power1.inOut', onUpdate: paint }, tEnd - 0.2)
      .to(labels, { opacity: 0.6, duration: 0.6 }, tEnd)
      .to('#aend', { opacity: 1, y: 0, duration: 0.8, ease: 'power2.out' }, tEnd)
      .to({}, { duration: 0.8 });
    gsap.set('#aend', { y: 20 }); gsap.set(labels, { x: -14 });
  }

  /* ---------- the climax: close on the flower, then the camera pulls back ---------- */
  function setupClimax() {
    var bn = document.getElementById('brideBanner'); if (!bn || REDUCED) return;
    bn.style.setProperty('--sh', 0);
    var ct = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: bn, start: 'top top', end: '+=' + (MOBILE ? 160 : 200) + '%', pin: true, scrub: 1 } });
    ct.fromTo('#brideBg', { scale: MOBILE ? 1.7 : 1.9 }, { scale: 1, duration: 3, ease: 'power2.inOut' }, 0)
      .to(bn, { '--sh': 1, duration: 1.2, ease: 'power1.in' }, 2.1)
      .from('#brideBanner .tx > *', { y: 40, opacity: 0, duration: 0.8, stagger: 0.18, ease: 'power3.out' }, 2.6)
      .to({}, { duration: 0.6 });
  }

  /* ---------- prices: every digit rolls into place, like an old exchange board ---------- */
  function roll(el) {
    var txt = el.textContent; if (!/\d/.test(txt) || el.dataset.rolled === txt) return;
    el.dataset.rolled = txt; el.classList.add('odo');
    el.innerHTML = txt.split('').map(function (ch) {
      if (!/\d/.test(ch)) return '<span class="c"><i>' + ch + '</i></span>';
      var col = ''; for (var d = 0; d <= 9; d++) col += d + '<br>';
      return '<span class="c"><i style="transform:translateY(0)">' + col + '</i></span>';
    }).join('');
    var cols = el.querySelectorAll('.c i'), digits = txt.replace(/[^\d]/g, '').split(''), k = 0;
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      txt.split('').forEach(function (ch, i) { if (/\d/.test(ch)) { var c = cols[i]; c.style.transitionDelay = (k++ * 0.06) + 's'; c.style.transform = 'translateY(' + (-1.15 * +ch) + 'em)' } });
    }) });
  }
  var qh = document.getElementById('quotesHome');
  if (qh) new IntersectionObserver(function (es) { if (es[0].isIntersecting) qh.querySelectorAll('.sell .num').forEach(roll) }, { threshold: 0.4 }).observe(qh);

  function go() { setupAnat(window.GM_SITE, window.GM_money); setupClimax(); ScrollTrigger.sort && ScrollTrigger.sort(); ScrollTrigger.refresh() }
  if (window.GM_SITE) go(); else document.addEventListener('gm:ready', go, { once: true });

  window.ringRefresh = function () { size(); ScrollTrigger.refresh() };
  addEventListener('load', function () { ScrollTrigger.refresh() });
})();

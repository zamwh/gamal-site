/* جمال المشرقي — cinematic scroll scene (prototype). Scroll drives everything; nothing autoplays. */
(function () {
  'use strict';
  var PIECES = {
    ring: { src: 'img/scene_ring.webp', ratio: 1114 / 1402, k: 'صنعة يدوية · عيار 21', t1: 'تفاصيل', t2: 'تُرى عن قرب' },
    medallion: { src: 'img/scene_medallion.webp', ratio: 1108 / 1402, k: 'قلادة الميدالية · عيار 21', t1: 'شغل يدوي', t2: 'يليق بليلة العمر' }
  };
  var key = new URLSearchParams(location.search).get('p'); if (!PIECES[key]) key = 'ring';
  var P = PIECES[key];
  document.querySelectorAll('#pick a').forEach(function (a) { a.classList.toggle('on', a.dataset.p === key) });
  document.querySelectorAll('#obj img').forEach(function (im) { im.src = P.src });
  ['halo', 'spec'].forEach(function (id) { var el = document.getElementById(id); el.style.backgroundImage = id === 'halo' ? 'url(' + P.src + ')' : el.style.backgroundImage; if (id === 'spec') { el.style.webkitMaskImage = 'url(' + P.src + ')'; el.style.maskImage = 'url(' + P.src + ')' } });
  document.getElementById('obj').style.aspectRatio = P.ratio;
  document.getElementById('capK').textContent = P.k; document.getElementById('capT1').textContent = P.t1;
  document.getElementById('capT2').innerHTML = '<em>' + P.t2 + '</em>';

  var REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MOBILE = matchMedia('(max-width: 760px), (hover: none)').matches;
  if (REDUCED || !window.gsap || !window.ScrollTrigger) return;   // calm, static version (CSS)

  gsap.registerPlugin(ScrollTrigger);
  ScrollTrigger.config({ ignoreMobileResize: true });
  var obj = '#obj', blur = function (v) { return MOBILE ? 'none' : 'blur(' + v + 'px)' };

  // starting point: far away, small, lying at an angle
  gsap.set(obj, { scale: 0.2, rotationX: 30, rotationY: -34, rotationZ: -12, z: -200, opacity: 0, filter: blur(8), transformOrigin: '50% 55%' });
  gsap.set('#amb', { scale: 0.55, opacity: 0 });
  gsap.set('#capT1, #capT2', { yPercent: 110 }); gsap.set('#capK', { opacity: 0, y: 12 });
  gsap.set('#cap', { opacity: 1 });

  var tl = gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: {
      trigger: '#film', start: 'top top', end: '+=' + (MOBILE ? 320 : 380) + '%', pin: true, scrub: 1.1, anticipatePin: 1,
      onUpdate: function (st) { bar.style.transform = 'scaleX(' + st.progress.toFixed(3) + ')'; progress = st.progress }
    }
  });
  var bar = document.getElementById('bar'), progress = 0;

  // 1) appears from the dark, far away
  tl.to(obj, { opacity: 1, filter: blur(0), duration: 1.2, ease: 'power1.out' }, 0)
    .to('#amb', { opacity: 0.7, duration: 1.5, ease: 'sine.out' }, 0)
  // 2–3) turns slowly in depth while it comes closer
    .to(obj, { rotationY: 24, duration: 5, ease: 'sine.inOut' }, 0.4)
    .to(obj, { rotationX: 4, rotationZ: 3, duration: 5, ease: 'power2.inOut' }, 0.4)
    .to(obj, { scale: 1, z: 0, duration: 5, ease: 'power2.inOut' }, 0.4)
    .to('#amb', { scale: 1.1, duration: 5, ease: 'sine.inOut' }, 0.4)
    .to('#floor', { opacity: 0.75, duration: 3, ease: 'sine.inOut' }, 2.4)
    .fromTo('#spec', { backgroundPosition: '125% 0' }, { backgroundPosition: '-25% 0', duration: 3.6, ease: 'sine.inOut' }, 1.8)
  // 4) the hero moment: large, almost still, words rise from behind a mask
    .to('#capK', { opacity: 1, y: 0, duration: 1, ease: 'power2.out' }, 4.2)
    .to(obj, { y: () => -innerHeight * 0.05, duration: 1.4, ease: 'sine.inOut' }, 4.0)
    .to('#capT1', { yPercent: 0, duration: 1.1, ease: 'power3.out' }, 4.4)
    .to('#capT2', { yPercent: 0, duration: 1.1, ease: 'power3.out' }, 4.65)
    .to(obj, { rotationY: 12, rotationZ: 0, duration: 1.8, ease: 'sine.inOut' }, 5.4)
    .fromTo('#spec', { backgroundPosition: '125% 0' }, { backgroundPosition: '-25% 0', duration: 1.8, ease: 'sine.inOut', immediateRender: false }, 5.4)
    .to('#capT1, #capT2', { yPercent: -110, duration: 0.9, ease: 'power2.in', stagger: 0.12 }, 6.8)
    .to('#capK', { opacity: 0, duration: 0.8 }, 6.9)
    .to(obj, { y: 0, duration: 1.4, ease: 'sine.inOut' }, 7.0)
  // 5) it withdraws into the depth of the scene and fades
    .to(obj, { scale: 0.1, z: -400, rotationY: -38, rotationX: 22, duration: 2.6, ease: 'power3.in' }, 7.1)
    .to(obj, { opacity: 0, filter: blur(10), duration: 1.4, ease: 'power2.in' }, 8.3)
    .to('#floor', { opacity: 0, duration: 1, ease: 'power1.in' }, 7.4)
    .to('#amb', { opacity: 0, scale: 0.6, duration: 2.2, ease: 'power2.in' }, 7.6)
  // 6) the next section rises in
    .to('#curtain', { height: '100%', duration: 1.4, ease: 'power2.inOut' }, 9.1);

  gsap.from('.next > *', { y: 40, opacity: 0, duration: 1.4, ease: 'power3.out', stagger: 0.12, scrollTrigger: { trigger: '#next', start: 'top 70%' } });

  // gold dust: a few slow specks at different depths (cheap, paused when the scene is off screen)
  var cv = document.getElementById('dust'), cx = cv.getContext('2d'), dpr = Math.min(2, devicePixelRatio || 1), W, H, D = [], on = true;
  function size() { W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0) }
  size(); addEventListener('resize', size);
  for (var i = 0; i < (MOBILE ? 34 : 70); i++) D.push({ x: Math.random(), y: Math.random(), z: 0.2 + Math.random() * 0.8, r: 0.4 + Math.random() * 1.4, t: Math.random() * 6.28, s: 0.0006 + Math.random() * 0.0012 });
  new IntersectionObserver(function (e) { on = e[0].isIntersecting }).observe(document.getElementById('film'));
  (function loop(now) {
    requestAnimationFrame(loop); if (!on) return;
    cx.clearRect(0, 0, W, H);
    var glow = Math.sin(Math.min(1, progress / 0.7) * Math.PI) * 0.8 + 0.2;
    for (var j = 0; j < D.length; j++) {
      var d = D[j]; d.t += 0.012; d.y -= d.s * d.z;
      if (d.y < -0.05) { d.y = 1.05; d.x = Math.random() }
      var y = ((d.y - progress * 0.35 * d.z) % 1 + 1) % 1, a = (0.25 + 0.75 * (0.5 + 0.5 * Math.sin(d.t))) * d.z * glow;
      var px = d.x * W, py = y * H, r = d.r * (0.6 + d.z);
      var g = cx.createRadialGradient(px, py, 0, px, py, r * 4);
      g.addColorStop(0, 'rgba(255,236,190,' + (a * 0.9).toFixed(3) + ')'); g.addColorStop(1, 'rgba(217,184,114,0)');
      cx.fillStyle = g; cx.beginPath(); cx.arc(px, py, r * 4, 0, 6.283); cx.fill();
    }
  })();
})();

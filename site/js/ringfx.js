/* ring scene on the home page: the ring comes out of the dark, settles beside the text, then the four sections arrive. */
(function () {
  'use strict';
  if (!window.gsap || !window.ScrollTrigger || !document.getElementById('rfx')) return;
  var REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var MOBILE = matchMedia('(max-width: 760px)').matches;
  gsap.registerPlugin(ScrollTrigger);
  ScrollTrigger.config({ ignoreMobileResize: true });

  // final resting place of the ring: left side (desktop) or upper part (phone)
  var endX = function () { return MOBILE ? 0 : -innerWidth * 0.27 };
  var endY = function () { return MOBILE ? -innerHeight * 0.26 : 0 };

  // a slow, endless turn of its own — the ring is alive even when you stop scrolling
  var idle = gsap.timeline({ repeat: -1, yoyo: true, paused: REDUCED });
  idle.to('#rspin', { rotationY: 26, rotationZ: 2, duration: 4.5, ease: 'sine.inOut' })
      .fromTo('#rspec', { backgroundPosition: '125% 0' }, { backgroundPosition: '-25% 0', duration: 4.5, ease: 'sine.inOut' }, 0);
  gsap.set('#rspin', { rotationY: -22, rotationZ: -2 });

  if (REDUCED) {
    gsap.set('#robj', { x: endX, y: endY, opacity: 1 }); gsap.set('#ramb', { opacity: 1, x: endX });
    window.ringRefresh = function () { }; return;
  }

  gsap.set('#robj', { scale: 0.22, rotationX: 28, opacity: 0, transformPerspective: 1400, transformOrigin: '50% 55%' });
  gsap.set('#ramb', { opacity: 0, scale: 0.6, xPercent: 0 });
  gsap.set('#rk, #rlead', { opacity: 0, y: 18 });
  gsap.set('#rt1, #rt2', { yPercent: 110 });
  gsap.set('#rcards .rc', { opacity: 0, y: 40 });

  var tl = gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: { trigger: '#rfx', start: 'top top', end: '+=' + (MOBILE ? 230 : 260) + '%', pin: '.rstage', scrub: 1, anticipatePin: 1, invalidateOnRefresh: true }
  });
  // 1) out of the dark, far away
  tl.to('#robj', { opacity: 1, duration: 1, ease: 'power1.out' }, 0)
    .to('#ramb', { opacity: 1, duration: 1.4, ease: 'sine.out' }, 0)
  // 2–3) turns in depth and comes closer, gliding to its side
    .to('#robj', { scale: 1, rotationX: 0, duration: 3.4, ease: 'power2.inOut' }, 0.3)
    .to('#robj', { x: endX, y: endY, duration: 3.4, ease: 'power3.inOut' }, 0.6)
    .to('#ramb', { x: function () { return MOBILE ? 0 : -innerWidth * 0.05 }, scale: 1, duration: 3.4, ease: 'sine.inOut' }, 0.6)
  // 4) the words beside it
    .to('#rk', { opacity: 1, y: 0, duration: 0.8, ease: 'power2.out' }, 2.6)
    .to('#rt1', { yPercent: 0, duration: 1, ease: 'power3.out' }, 2.8)
    .to('#rt2', { yPercent: 0, duration: 1, ease: 'power3.out' }, 3.0)
    .to('#rlead', { opacity: 1, y: 0, duration: 1, ease: 'power2.out' }, 3.3)
  // 5) the four sections arrive, one after another
    .to('#rcards .rc', { opacity: 1, y: 0, duration: 1.1, ease: 'power3.out', stagger: 0.28 }, 4.3)
    .to({}, { duration: 1 });   // a short breath before the page moves on

  // gold dust, paused off screen
  var cv = document.getElementById('rdust'), cx = cv.getContext('2d'), dpr = Math.min(2, devicePixelRatio || 1), W, H, D = [], on = false;
  function size() { W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0) }
  size(); addEventListener('resize', size);
  for (var i = 0; i < (MOBILE ? 26 : 54); i++) D.push({ x: Math.random(), y: Math.random(), z: 0.2 + Math.random() * 0.8, r: 0.4 + Math.random() * 1.3, t: Math.random() * 6.28, s: 0.0005 + Math.random() * 0.001 });
  new IntersectionObserver(function (e) { on = e[0].isIntersecting; on ? idle.play() : idle.pause() }).observe(document.getElementById('rfx'));
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
  window.ringRefresh = function () { size(); ScrollTrigger.refresh() };
  addEventListener('load', function () { ScrollTrigger.refresh() });
})();

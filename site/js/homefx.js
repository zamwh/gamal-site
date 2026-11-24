/* home motion: only at the top. The grand piece comes closer, turns a little, and withdraws into the shop. */
(function () {
  'use strict';
  var REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches, MOBILE = matchMedia('(max-width: 760px)').matches;
  if (window.gsap && window.ScrollTrigger && !REDUCED && document.getElementById('h3piece')) {
    gsap.registerPlugin(ScrollTrigger);
    ScrollTrigger.config({ ignoreMobileResize: true });
    gsap.set('#h3piece', { transformPerspective: 1400, transformOrigin: '50% 40%' });
    var ht = gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: '#hero', start: 'top top', end: '+=' + (MOBILE ? 90 : 110) + '%', pin: '#h3stage', scrub: 1 } });
    ht.to('#h3piece', { scale: MOBILE ? 1.15 : 1.22, y: function () { return innerHeight * 0.05 }, rotationY: 14, rotationZ: -3, duration: 1.3, ease: 'power2.inOut' }, 0)
      .to('#h3copy', { opacity: 0, y: -40, duration: 0.6, ease: 'power2.in' }, 0.15)
      .to('#h3piece', { scale: 0.35, z: -300, opacity: 0, rotationY: -10, duration: 1, ease: 'power3.in' }, 1.3);
    window.ringRefresh = function () { ScrollTrigger.refresh() };
    addEventListener('load', function () { ScrollTrigger.refresh() });
  }
  // prices count up into place when they come into view
  function roll(el) {
    var txt = el.textContent, target = parseInt(txt.replace(/[^\d]/g, ''), 10);
    if (!target || el.dataset.rolled === txt || REDUCED) return; el.dataset.rolled = txt;
    var from = Math.round(target * 0.92), t0 = performance.now(), D = 1500;
    (function step(now) { var k = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - k, 4); el.textContent = Math.round(from + (target - from) * e).toLocaleString('en-US'); if (k < 1) requestAnimationFrame(step); else { el.textContent = txt; el.dataset.rolled = txt } })(t0);
  }
  var qh = document.getElementById('quotesHome');
  if (qh) new IntersectionObserver(function (es) { if (es[0].isIntersecting) qh.querySelectorAll('.sell .num').forEach(roll) }, { threshold: 0.4 }).observe(qh);
})();

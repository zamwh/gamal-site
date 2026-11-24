/* Home v6: hero with a featured piece, three story cards, trust line. Real stock only (window.GM_SITE). */
(function () {
  var $ = function (s, r) { return (r || document).querySelector(s) };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] }) };
  var EN = function () { return document.documentElement.lang === 'en' };
  var t = function (ar, en) { return EN() ? en : ar };
  var title = function (p) { return EN() && p.title_en ? p.title_en : p.title };
  var money = function (v) { return window.GM_money ? window.GM_money(v) : Number(v).toLocaleString('en-US') };
  var FEAT = [], fi = 0, ft = null;

  function featHTML(p) {
    return '<div class="ey">' + t('قطعة مختارة', 'Featured piece') + '</div><h3>' + esc(title(p)) + '</h3><small>' + t('عيار ', '') + p.karat + t('', 'K') + ' · ' + p.weight + t(' جرام', ' g') + '</small>' +
      '<div class="im lx-swap" style="background-image:url(\'' + esc(p.photo) + '\')"></div><div class="pr">' + money(p.price) + '</div>' +
      '<a class="lx-lnk" href="#p-' + esc(p.code) + '">' + t('شاهد القطعة ←', 'View piece →') + '</a>' +
      '<div class="lx-dots">' + FEAT.map(function (_, i) { return '<i data-i="' + i + '" class="' + (i === fi ? 'on' : '') + '"></i>' }).join('') + '</div>';
  }
  function showFeat(i) {
    if (!FEAT.length) return;
    fi = (i + FEAT.length) % FEAT.length;
    var box = $('#lxFeat'); box.innerHTML = featHTML(FEAT[fi]);
    box.querySelectorAll('.lx-dots i').forEach(function (d) { d.onclick = function (e) { e.preventDefault(); showFeat(+d.dataset.i) } });
    clearTimeout(ft); ft = setTimeout(function () { showFeat(fi + 1) }, 8000);
  }
  function card(eye, p, desc, href, tag, img) {
    return '<a class="lxc lx-rise" href="' + href + '"><div class="tx">' + (tag ? '<span class="tag">' + eye + '</span>' : '<div class="ey">' + eye + '</div>') +
      '<h3>' + esc(p ? title(p) : desc[0]) + '</h3><p>' + esc(desc[1]) + '</p>' + (p ? '<div class="pr">' + money(p.price) + '</div>' : '') +
      '<span class="lx-lnk">' + t('شاهد ←', 'View →') + '</span></div><div class="im" style="background-image:url(\'' + esc(img) + '\')"></div></a>';
  }
  function render() {
    var S = window.GM_SITE; if (!S || !$('#lux')) return;
    var ps = S.pieces.filter(function (p) { return p.photo && p.status === 'available' });
    if (!ps.length) return;
    var byPrice = ps.slice().sort(function (a, b) { return b.price - a.price });
    var main = ps.find(function (p) { return /وردة|ورد/.test(p.title) && /حزام/.test(p.title) }) || byPrice[0];
    var mi = $('#lxMainImg'); mi.src = main.photo; mi.alt = title(main); $('#lxMain').href = '#p-' + main.code;
    FEAT = byPrice.filter(function (p) { return p.code !== main.code }).slice(0, 3);
    showFeat(fi);
    var necklace = ps.find(function (p) { return p.kind === 'عقد' && p.code !== main.code }) || ps[0];
    var newest = ps.slice().reverse().find(function (p) { return p.code !== main.code && p.code !== necklace.code }) || ps[1] || ps[0];
    var setP = ps.find(function (p) { return p.kind === 'طقم' && p.code !== main.code }) || ps[0];
    $('#lxCards').innerHTML =
      card(t('مجموعة مميزة', 'Signature'), null, [t('عقود بتكوين مركزي', 'Centre-piece Necklaces'), t('قطع تبني حضورها من الوسط، بنقش مرتب.', 'Pieces built around a central motif, with orderly engraving.')], '#collections', false, necklace.photo) +
      card(t('وصل حديثاً', 'New arrival'), newest, ['', (newest.weight + t(' جرام · عيار 21', ' g · 21K'))], '#p-' + newest.code, true, newest.photo) +
      card(t('باقة العروس', 'Bridal'), null, [t('تنسيق متكامل ليوم العمر', 'A Complete Wedding Set'), t('عقد وحلق وكف وحزام، متناسقة.', 'Necklace, earrings, hand piece and belt, all matching.')], '#bride', false, setP.photo);
    rise();
  }
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (es) {
    es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } })
  }, { threshold: 0.15 }) : null;
  function rise() {
    document.querySelectorAll('.lx-rise:not(.in), .lx-trust>div:not(.lx-rise), #shop .card:not(.lx-rise)').forEach(function (el, i) {
      if (!el.classList.contains('lx-rise')) el.classList.add('lx-rise');
      el.style.transitionDelay = (i % 4) * 70 + 'ms';
      if (io) io.observe(el); else el.classList.add('in');
    });
  }
  document.addEventListener('gm:ready', render);
  document.addEventListener('gm:lang', render);
  if (window.GM_SITE) render();
  new MutationObserver(function () { rise() }).observe(document.body, { childList: true, subtree: true });
})();

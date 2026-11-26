/* جمال المشرقي — v3 site logic: pages with addresses, cinematic scroll, real data */
(function () {
  'use strict';
  function hideSplash() { var s = document.getElementById('splash'); if (s) s.classList.add('out') }
  window.addEventListener('error', hideSplash); setTimeout(hideSplash, 3500);
  var $ = function (s, r) { return (r || document).querySelector(s) }, $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)) };
  var ONLINE = location.protocol.indexOf('http') === 0;
  // each opened page = a fresh conversation, so the assistant never answers old, invisible messages
  var CHAT_ID = ((window.T && window.T.session) || 's') + '-' + Math.random().toString(36).slice(2, 7);
  var T = window.T || function () { };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] }) };
  var fmt = function (n) { return Math.round(n).toLocaleString('en-US') };
  var clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)) };
  var lerp = function (a, b, t) { return a + (b - a) * t };
  var ease = function (t) { return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2 };
  var REDUCED = matchMedia('(prefers-reduced-motion:reduce)').matches, TOUCH = matchMedia('(hover:none)').matches;

  /* ---------- demo data (used when the page runs without the server) ---------- */
  var DEMO = {
    v: 2, demo: true, deposit_pct: 10, ai: false,
    prices: { k21: { sell: 52000, buy: 50000, chg: 500 }, pound: { sell: 416000, buy: 400000, chg: 4000 }, updated: '', rates: { sar: 140, usd: 535 } },
    history: [], links: { tiktok: 'https://www.tiktok.com/@almashraqi.gold8', instagram: 'https://www.instagram.com/almashreqi_gold', facebook: 'https://www.facebook.com/share/1JkbaD2t5t/', whatsapp: '+967770088801' },
    branches: [{ n: 'جمال المشرقي للذهب والمجوهرات', addr: 'بجوار البوابة الرئيسية لمركز جرعان، إب', one: true }],
    policy: { deposit: 'الحجز بعربون 10% من قيمة القطعة يحفظها 24 ساعة من تأكيده ولا يثبّت سعر الذهب؛ السعر النهائي بسعر الذهب يوم إتمام البيع ويُخصم منه العربون. لا يُعد الحجز مؤكداً إلا بعد مراجعة المحاسب لوصول التحويل. الاستلام من المحل فقط بفاتورة موقعة من الطرفين.', full: 'شراء بتحويل كامل قيمة القطعة: يثبت السعر بسعر الذهب وقت التحويل، ولا يُعد الشراء رسمياً إلا بعد مراجعة المحاسب لوصول المبلغ كاملاً. بعد التأكيد تستلم القطعة من المحل بفاتورة رسمية موقعة من الطرفين.' },
    pieces: [
      ['D000001', 'طقم عروس متكامل بالورد', 'طقم', 148.6, 'set', 'فخم', 'عرس', 'الفرع الأول', 'طقم كامل: عقد بشراشيب، حلق، كف بخواتم، وحزام مدوّر.'],
      ['D000002', 'عقد صدر شبك', 'عقد', 96.4, 'bib', 'فخم', 'عرس', 'الفرع الأول', 'عقد صدر عريض بتصميم الشبك والمعيّنات.'],
      ['D000003', 'طقم الهلال بالشراشيب', 'طقم', 55.6, 'crescent', 'كلاسيكي', 'عرس', 'الفرع الثاني', 'عقد بتعليقة هلال مزدوج وشراشيب، مع حلق.'],
      ['D000004', 'طقم سلاسل بالمستطيل', 'طقم', 38.5, 'chains', 'كلاسيكي', 'خطوبة', 'الفرع الأول', 'عقد طويل بتعليقة مستطيلة متدرجة، مع حلق.'],
      ['D000005', 'عقد مجدول بالقطرات', 'عقد', 58.2, 'velvet', 'كلاسيكي', 'عرس', 'الفرع الثاني', 'عقد مجدول بثلاث قطرات مخرّمة، مع حلق.'],
      ['D000006', 'كردان كرات مع أسورة', 'عقد', 74.0, 'collar', 'فخم', 'عرس', 'الفرع الثالث', 'كردان عريض من الكرات المنقوشة مع أسورة.'],
      ['D000007', 'طقم الوردة الطويل مع الحزام', 'طقم', 120.0, 'flower', 'فخم', 'عرس', 'الفرع الثالث', 'عقد طويل بوردة وشراشيب، حزام بطبقات، وحلق.']
    ].map(function (a) { return { code: a[0], title: a[1], kind: a[2], karat: 21, weight: a[3], price: Math.round(a[3] * 55000), photo: 'img/demo/' + a[4] + '.jpg', style: a[5], occasion: a[6], branch: a[7], description: a[8], status: 'available' } })
  };
  var SITE = DEMO, BY = {};

  /* ---------- currency ---------- */
  var CUR = 'YER';
  try { CUR = localStorage.getItem('gm_cur') || 'YER' } catch (e) { }
  function conv(yer, cur) { var r = (SITE.prices && SITE.prices.rates) || {}; cur = cur || CUR; if (cur === 'SAR' && r.sar) return yer / r.sar; if (cur === 'USD' && r.usd) return yer / r.usd; return yer }
  function curLbl(cur) { cur = cur || CUR; return cur === 'SAR' ? 'ر.س' : cur === 'USD' ? '$' : 'ر.ي' }
  function money(yer, cur) { return fmt(conv(yer, cur)) + ' ' + curLbl(cur) }
  function moneyH(yer, cur) { return '<span class="num">' + fmt(conv(yer, cur)) + '</span><span class="cur">' + curLbl(cur) + '</span>' }
  $$('#cur button').forEach(function (b) { b.onclick = function () { CUR = b.dataset.c; try { localStorage.setItem('gm_cur', CUR) } catch (e) { } renderAll(); route() } });

  /* ---------- theme: dark by default; day mode is the visitor's choice, remembered on this device ---------- */
  var mode = 'night';
  try { if (localStorage.getItem('gm_mode3') === 'day') mode = 'day' } catch (e) { }
  function applyMode() { document.documentElement.classList.toggle('day', mode === 'day'); $('meta[name=theme-color]').content = mode === 'day' ? '#f5f0e6' : '#070605'; $('#modeBtn').setAttribute('aria-label', mode === 'day' ? 'الوضع الليلي' : 'الوضع النهاري') }
  $('#modeBtn').onclick = function () { mode = mode === 'day' ? 'night' : 'day'; try { localStorage.setItem('gm_mode3', mode) } catch (e) { } applyMode() };
  applyMode();

  var tt; function toast(m) { var t = $('#toast'); t.textContent = m; t.classList.add('on'); clearTimeout(tt); tt = setTimeout(function () { t.classList.remove('on') }, 2600) }
  function wa(text) { var n = String((SITE.links || {}).whatsapp || '').replace(/\D/g, ''); return n ? 'https://wa.me/' + n + (text ? '?text=' + encodeURIComponent(text) : '') : '' }
  function bindLinks() {
    $$('[data-link]').forEach(function (a) {
      var k = a.dataset.link, u = k === 'whatsapp' ? wa('السلام عليكم، أبغى أستفسر عن مجموعتكم') : (SITE.links || {})[k];
      if (u) { a.href = u; a.target = '_blank'; a.rel = 'noopener' }
      a.onclick = function (e) { if (!u) { e.preventDefault(); toast('الرابط يُضاف قريباً') } T(k === 'whatsapp' ? 'whatsapp_click' : 'social_click', null, k) };
    });
  }

  /* ---------- price card: sell big, buy small, the pound below; "how much is your gold today" and the price history inside ---------- */
  var AR_D = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  var AR_M = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  function arWhen(s) {   // the shop's own clock, as typed: "2026-11-23 19:11:41" → "الاثنين 23 نوفمبر · 7:11 م"
    var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/); if (!m) return '';
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])), h = +m[4];
    return AR_D[d.getUTCDay()] + ' ' + (+m[3]) + ' ' + AR_M[+m[2] - 1] + ' · ' + (h % 12 || 12) + ':' + m[5] + ' ' + (h < 12 ? 'ص' : 'م');
  }
  function arDay(s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? (+m[3]) + ' ' + AR_M[+m[2] - 1] : String(s || '') }
  var PC = { tab: 'calc', unit: 'g', qty: '10' }, calcSent = false;
  var IC_PLUS = '<svg class="i" viewBox="0 0 24 24"><path d="M12 6v12M6 12h12"/></svg>', IC_MINUS = '<svg class="i" viewBox="0 0 24 24"><path d="M6 12h12"/></svg>';
  function priceCardHTML(sx) {
    var p = SITE.prices, k = p.k21, pd = p.pound, n = function (v) { return '<span class="num">' + fmt(conv(v)) + '</span>' };
    var fresh = p.updated && p.updated.slice(0, 10) === new Date().toISOString().slice(0, 10), when = p.updated ? arWhen(p.updated) : '';
    var hist = (SITE.history || []).slice(-7).reverse();
    return '<div class="g2pc-h"><div><span class="eyebrow">بورصة الذهب</span><h2>سعر <em>اليوم</em></h2></div>' +
      (when ? '<span class="g2pc-up"><span>' + (fresh ? 'آخر تحديث' : 'آخر سعر سجّله المحل') + '</span><br>' + esc(when) + '</span>' : '') + '</div>' +
      '<div class="g2pc-g"><div class="g2pc-r1"><span>جرام عيار 21</span>' + (k.chg ? '<span class="g2pc-chg' + (k.chg < 0 ? ' dn' : '') + '">' + (k.chg > 0 ? '▲ ' : '▼ ') + n(Math.abs(k.chg)) + '</span>' : '') + '</div>' +
      '<div class="g2pc-r2"><div class="g2pc-sell"><span>بيع</span><b class="num">' + fmt(conv(k.sell)) + '</b><span>' + curLbl() + '</span></div>' +
      '<div class="g2pc-buy"><span>شراء</span><b class="num">' + fmt(conv(k.buy)) + '</b></div></div></div>' +
      '<div class="g2pc-pd"><span>الجنيه الذهب</span><span class="g2pc-pv"><span>بيع</span>' + n(pd.sell) + '<i></i><span>شراء</span>' + n(pd.buy) + '</span></div>' +
      '<div class="g2-tabs" role="tablist" aria-label="أدوات السعر"><button type="button" role="tab" data-tab="calc">بكم ذهبك اليوم؟</button><button type="button" role="tab" data-tab="hist">سجل الأسعار</button></div>' +
      '<div class="g2-pan" data-pan="calc" role="tabpanel"><div class="g2-units"><button type="button" data-u="g">بالجرام</button><button type="button" data-u="p">بالجنيه</button></div>' +
      '<div class="g2-step"><button type="button" data-q="1" aria-label="زيادة">' + IC_PLUS + '</button><label><input type="number" inputmode="decimal" min="0" step="any"><span></span></label><button type="button" data-q="-1" aria-label="إنقاص">' + IC_MINUS + '</button></div>' +
      '<div class="g2-pre"></div><div class="g2-res"><small>قيمة ذهبك (عيار 21) اليوم تقريباً</small><b></b><span class="g2-rate"></span></div>' +
      '<p class="g2-note">الأسعار تقديرية وليست نهائية، وقد يختلف السعر حسب حالة الذهب. ونقيّم كل قطعة في المحل بما تستحق.</p></div>' +
      '<div class="g2-pan g2-hist" data-pan="hist" role="tabpanel" hidden><div class="g2pc-r1"><span>سعر بيع الجرام</span><span>' + curLbl() + '</span></div>' +
      '<svg class="spark" id="g2sp' + sx + '" preserveAspectRatio="none" aria-hidden="true"></svg>' +
      hist.map(function (h) { return '<div class="g2-hrow"><span>' + esc(arDay(h.d)) + '</span>' + n(h.v) + '</div>' }).join('') +
      (hist.length < 2 ? '<p class="g2-note">يظهر رسم السعر بعد تسجيل أسعار أكثر من يوم.</p>' : '') + '</div>';
  }
  function pcUpdate(root) {
    var p = SITE.prices, pound = PC.unit === 'p', rate = pound ? p.pound.buy : p.k21.buy;
    var q = parseFloat(String(PC.qty).replace('٫', '.').replace(',', '.')) || 0;
    $('.g2-res b', root).innerHTML = q > 0 ? moneyH(q * rate) : '—';
    $('.g2-rate', root).innerHTML = '<span>على سعر الشراء</span> ' + moneyH(rate) + ' <span>' + (pound ? 'للجنيه' : 'للجرام') + '</span>';
    var inp = $('.g2-step input', root); if (document.activeElement !== inp) inp.value = PC.qty;
    inp.setAttribute('aria-label', pound ? 'عدد الجنيهات' : 'الوزن بالجرام'); $('.g2-step label span', root).textContent = pound ? 'جنيه' : 'جرام';
    $('.g2-pre', root).innerHTML = (pound ? [1, 2, 5, 10] : [5, 10, 20, 50]).map(function (v) { var on = +PC.qty === v; return '<button type="button" data-pre="' + v + '" class="' + (on ? 'on' : '') + '" aria-pressed="' + on + '">' + v + ' ' + (pound ? 'جنيه' : 'جرام') + '</button>' }).join('');
    $$('.g2-units button', root).forEach(function (b) { var on = b.dataset.u === PC.unit; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on) });
    $$('.g2-tabs button', root).forEach(function (b) { var on = b.dataset.tab === PC.tab; b.classList.toggle('on', on); b.setAttribute('aria-selected', on) });
    $$('.g2-pan', root).forEach(function (x) { x.hidden = x.dataset.pan !== PC.tab });
  }
  function bindPriceCard(root) {
    root.onclick = function (e) {
      var b = e.target.closest('button'); if (!b || !root.contains(b)) return;
      if (b.dataset.tab) PC.tab = b.dataset.tab;
      else if (b.dataset.u) { if (PC.unit !== b.dataset.u) { PC.unit = b.dataset.u; PC.qty = PC.unit === 'p' ? '1' : '10' } }
      else if (b.dataset.q) PC.qty = String(Math.max(0, Math.round(((parseFloat(PC.qty) || 0) + Number(b.dataset.q)) * 100) / 100));
      else if (b.dataset.pre) PC.qty = b.dataset.pre;
      else return;
      pcUpdate(root); if (PC.tab === 'hist') spark($('.spark', root));
      if (!calcSent && !b.dataset.tab) { calcSent = true; T('calc_use') }
    };
    var inp = $('.g2-step input', root);
    inp.addEventListener('input', function () { PC.qty = inp.value; pcUpdate(root); if (!calcSent && inp.value) { calcSent = true; T('calc_use') } });
    pcUpdate(root);
  }
  function renderTicker() {
    var p = SITE.prices; if (!p) return;
    if ($('#hp21')) { $('#hp21').innerHTML = moneyH(p.k21.sell); $('#hpP').innerHTML = moneyH(p.pound.sell) }
    [['#priceHome', 'H'], ['#priceGold', 'G']].forEach(function (x) { var root = $(x[0]); if (!root) return; root.innerHTML = priceCardHTML(x[1]); bindPriceCard(root); spark($('.spark', root)) });
    if (p.updated && $('#upd2')) {   // prices are set by the shop by hand: say when, and say plainly if they are not from today
      var when = arWhen(p.updated), today = p.updated.slice(0, 10) === new Date().toISOString().slice(0, 10);
      $('#upd2').textContent = today ? 'أسعار المحل اليوم، يحدّثها المحل يدوياً (آخر تحديث ' + when + ') وقد تتغير خلال اليوم.' : 'آخر سعر سجّله المحل ' + when + '، وقد يختلف سعر اليوم. تأكد على واتساب.';
    }
  }

  /* ---------- home hero: the shop's name first, photos of its own pieces behind it ---------- */
  var G2H = 0, g2ht;
  function renderG2Hero() {
    var box = $('#g2hIms'); if (!box) return;
    var ph = SITE.pieces.filter(function (p) { return p.photo });
    var list = ph.filter(function (p) { return p.featured }).concat(ph.filter(function (p) { return !p.featured })).slice(0, 3);
    box.innerHTML = list.map(function (p) { return '<img src="' + esc(p.photo) + '" alt="' + esc(p.title) + '">' }).join('');
    $('#g2hDots').innerHTML = list.length > 1 ? list.map(function (p, i) { return '<button type="button" data-h="' + i + '" aria-label="الصورة ' + (i + 1) + '"><i></i></button>' }).join('') : '';
    $$('#g2hDots [data-h]').forEach(function (b) { b.onclick = function () { g2Go(+b.dataset.h, true) } });
    g2Go(Math.min(G2H, Math.max(0, list.length - 1)));
  }
  function g2Go(n, byHand) {
    var ims = $$('#g2hIms img'); if (!ims.length) return;
    G2H = (n + ims.length) % ims.length;
    ims.forEach(function (im, i) { im.classList.toggle('on', i === G2H) });
    $$('#g2hDots button').forEach(function (b, i) { b.classList.toggle('on', i === G2H); b.setAttribute('aria-pressed', i === G2H) });
    clearTimeout(g2ht); if (!REDUCED && ims.length > 1) g2ht = setTimeout(function () { g2Go(G2H + 1) }, byHand ? 9000 : 6000);
  }

  /* swipe the hero photos with a finger (or drag with the mouse): the photo follows the finger, the next one shows
     through, and it settles on release; up-and-down movement stays the page's own scrolling */
  (function () {
    var hero = $('#g2h'), box = $('#g2hIms'); if (!hero || !box) return;
    var x0 = 0, y0 = 0, t0 = 0, dx = 0, lock = null, on = false, cur = null, nxt = null, step = 0;
    var rtl = function () { return document.documentElement.dir !== 'ltr' };
    function start(x, y) { if ($$('#g2hIms img').length < 2) return; x0 = x; y0 = y; t0 = Date.now(); dx = 0; lock = null; on = true; cur = nxt = null }
    function move(x, y, e) {
      if (!on) return; dx = x - x0; var dy = y - y0;
      if (!lock) { if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return; lock = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'; if (lock === 'x') clearTimeout(g2ht) }
      if (lock !== 'x') return;
      if (e && e.cancelable) e.preventDefault();
      var L = $$('#g2hIms img'), s = (dx > 0) === rtl() ? 1 : -1;
      if (s !== step || !cur) { if (nxt) { nxt.style.opacity = '' } step = s; cur = L[G2H]; nxt = L[(G2H + s + L.length) % L.length] }
      var p = Math.min(1, Math.abs(dx) / (hero.clientWidth * .6));
      box.classList.add('drag');
      cur.style.transform = 'translateX(' + (dx * .35).toFixed(1) + 'px) scale(1.02)'; cur.style.opacity = (1 - p * .7).toFixed(3);
      nxt.style.opacity = p.toFixed(3);
    }
    function end() {
      if (!on) return; on = false; if (lock !== 'x') return;
      var fast = Math.abs(dx) > 30 && Date.now() - t0 < 300, go = Math.abs(dx) > hero.clientWidth * .18 || fast;
      box.classList.remove('drag'); box.classList.add('snap');
      if (cur) { cur.style.transform = ''; cur.style.opacity = '' } if (nxt) nxt.style.opacity = '';
      if (go) g2Go(G2H + step, true); else g2Go(G2H, true);
      setTimeout(function () { box.classList.remove('snap') }, 650);
      var stop = function (e) { e.preventDefault(); e.stopPropagation() };           // the swipe is not a tap on a button
      hero.addEventListener('click', stop, true); setTimeout(function () { hero.removeEventListener('click', stop, true) }, 350);
    }
    hero.addEventListener('touchstart', function (e) { if (e.touches.length === 1) start(e.touches[0].clientX, e.touches[0].clientY); else on = false }, { passive: true });
    hero.addEventListener('touchmove', function (e) { if (e.touches.length === 1) move(e.touches[0].clientX, e.touches[0].clientY, e) }, { passive: false });
    hero.addEventListener('touchend', end); hero.addEventListener('touchcancel', end);
    hero.addEventListener('pointerdown', function (e) { if (e.pointerType === 'mouse' && e.button === 0 && !e.target.closest('a,button')) { start(e.clientX, e.clientY); e.preventDefault() } });
    addEventListener('pointermove', function (e) { if (e.pointerType === 'mouse' && on) move(e.clientX, e.clientY, null) });
    addEventListener('pointerup', function (e) { if (e.pointerType === 'mouse') end() });
  })();

  /* ---------- home categories: two large tiles from the shop's own pieces, then the rest ---------- */
  function renderCatTiles() {
    var big = $('#g2cBig'), sm = $('#g2cSm'); if (!big || !sm) return;
    var col = function (k) { return COLS.filter(function (c) { return c.key === 'cat-' + k })[0] };
    var cnt = function (k) { var n = colItems(col(k)).length; return n ? n + (n > 2 ? ' قطع' : n === 2 ? ' قطعتين' : ' قطعة') : 'قريباً' };
    var go = '<span class="g2t-go" aria-hidden="true"><svg class="i ar"><use href="#s-arr"/></svg></span>';
    big.innerHTML = [['sets', 'الأطقم', 'أطقم كاملة للعرايس والمناسبات'], ['necklaces', 'العقود', 'عقود وكردانات بتصاميم حصرية']].map(function (c) {
      var its = colItems(col(c[0])).filter(function (p) { return p.photo }), pic = (its.filter(function (p) { return p.featured })[0] || its[0] || {}).photo || 'img/cat_' + c[0] + '.webp';
      return '<a class="g2t g2t-b" href="#collection-cat-' + c[0] + '"><img src="' + esc(pic) + '" alt="" loading="lazy"><span class="g2t-tx"><span><b>' + c[1] + '</b><small>' + c[2] + '</small></span>' + go + '</span></a>';
    }).join('');
    sm.innerHTML = [['bracelets', 'الأساور'], ['rings', 'الخواتم'], ['earrings', 'الحلق'], ['chains', 'السلاسل'], ['belts', 'الأحزمة']].map(function (c) {
      return '<a class="g2t g2t-s" href="#collection-cat-' + c[0] + '"><img src="img/cat_' + c[0] + '.webp" alt="" loading="lazy"><span class="g2t-tx"><span><b>' + c[1] + '</b><small>' + cnt(c[0]) + '</small></span>' + go + '</span></a>';
    }).join('') + (SITE.prices ? '<a class="g2t-pound" href="#gold"><small>الجنيه الذهب</small><b>الجنيهات</b><span>' + moneyH(SITE.prices.pound.sell) + '</span></a>' : '');
  }
  function spark(svg) {
    var h = (SITE.history || []).map(function (x) { return x.v }); if (h.length < 2) { svg.style.display = 'none'; if (svg.id === 'sparkGold') $('#sparkNote').textContent = 'يظهر رسم السعر بعد تسجيل أسعار أكثر من يوم.'; return }
    svg.style.display = ''; var W = svg.clientWidth || 600, H = svg.clientHeight || 110, mn = Math.min.apply(null, h), mx = Math.max.apply(null, h), r = mx - mn || 1;
    var pts = h.map(function (v, i) { return (i * W / (h.length - 1)).toFixed(1) + ',' + (H - 8 - (v - mn) / r * (H - 16)).toFixed(1) }).join(' ');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.innerHTML = '<defs><linearGradient id="sg' + svg.id + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d9b872" stop-opacity=".28"/><stop offset="1" stop-color="#d9b872" stop-opacity="0"/></linearGradient></defs><polygon fill="url(#sg' + svg.id + ')" points="0,' + H + ' ' + pts + ' ' + W + ',' + H + '"/><polyline fill="none" stroke="#d9b872" stroke-width="1.4" points="' + pts + '"/>';
  }

  /* ---------- hero slider (drag, arrows, progress) ---------- */
  var hi = 0, ht, HL = [];
  function renderHero() {
    HL = SITE.pieces.filter(function (p) { return p.photo }).slice(0, 5);
    $('#slides').innerHTML = HL.map(function (p, i) { return '<div class="slide' + (i ? '' : ' on') + '"><div class="im" style="background-image:url(\'' + esc(p.photo) + '\')"></div></div>' }).join('');
    $('#sTot').textContent = ('0' + HL.length).slice(-2); go(0);
    // no generated scene images on the site: every photo is the shop's own
  }
  function go(n) {
    var s = $$('#slides .slide'); if (!s.length) return;
    s[hi].classList.remove('on'); hi = (n + s.length) % s.length; s[hi].classList.add('on');
    $('#sIdx').textContent = ('0' + (hi + 1)).slice(-2);
    var pr = $('#prog'); pr.classList.remove('run'); void pr.offsetWidth; pr.classList.add('run');
    clearTimeout(ht); ht = setTimeout(function () { go(hi + 1) }, 7000);
  }
  $('#sNext').onclick = function () { go(hi + 1) }; $('#sPrev').onclick = function () { go(hi - 1) };
  (function () {
    var h = $('#hero'), x0 = null, dx = 0, moved = false;
    h.addEventListener('pointerdown', function (e) { if (e.target.closest('a,button')) return; x0 = e.clientX; dx = 0; moved = false });
    h.addEventListener('pointermove', function (e) { if (x0 !== null) { dx = e.clientX - x0; if (Math.abs(dx) > 8) moved = true } });
    function end() { if (x0 === null) return; if (Math.abs(dx) > 50) go(hi + (dx < 0 ? 1 : -1)); x0 = null }
    h.addEventListener('pointerup', end); h.addEventListener('pointercancel', end);
    
  })();

  /* ---------- collections ---------- */
  var COLS = [
    { key: 'new', t: 'وصل حديثاً', s: 'أحدث ما وصل للمحل', f: function (p) { return p.is_new } },
    { key: 'featured', t: 'مختارات المحل', s: 'قطع يختارها المحل لك', f: function (p) { return p.featured } },
    { key: 'bridal', t: 'أطقم العرايس', s: 'العقد والحلق والكف والحزام', f: function (p) { return p.kind === 'طقم' } },
    { key: 'necklaces', t: 'العقود والكردانات', s: 'صدر · مجدول · كردان', f: function (p) { return p.kind === 'عقد' } },
    { key: 'grand', t: 'الفخامة الكاملة', s: 'قطع تخطف الأنظار', f: function (p) { return p.style === 'فخم' } },
    { key: 'classic', t: 'الكلاسيكيات', s: 'أناقة هادئة لا تغيب', f: function (p) { return p.style === 'كلاسيكي' } },
    { key: 'engagement', t: 'للخطوبة', s: 'قطع أخف وأنعم', f: function (p) { return p.occasion === 'خطوبة' } }];
  // shop by category: what a piece is, read from its own name and type (a set with a belt also counts as a belt)
  var CATS = [['rings', 'خواتم', ['خاتم', 'خواتم']], ['chains', 'سلاسل', ['سلسل', 'سلاسل']], ['bracelets', 'أساور', ['أسورة', 'اسورة', 'أساور', 'اساور', 'بنجري', 'غوايش']],
              ['belts', 'أحزمة', ['حزام', 'احزمة']], ['necklaces', 'عقود وكردانات', ['عقد', 'كردان']], ['sets', 'أطقم', ['طقم', 'أطقم']], ['earrings', 'حلق', ['حلق', 'أقراط']]];
  CATS.forEach(function (c) { COLS.push({ key: 'cat-' + c[0], t: c[1], s: 'تسوّق حسب الفئة', f: function (p) { var h = (p.title || '') + ' ' + (p.kind || ''); return c[2].some(function (w) { return h.indexOf(w) >= 0 }) } }) });
  function renderCats() {
    var r = $('#catRow'); if (!r) return;
    r.innerHTML = CATS.map(function (c) {
      var n = colItems(COLS.filter(function (x) { return x.key === 'cat-' + c[0] })[0]).length;
      return '<a href="#collection-cat-' + c[0] + '" data-img="img/cat_' + c[0] + '.webp"><b>' + c[1] + '</b><small>' + (n ? n + (n > 2 ? ' قطع' : n === 2 ? ' قطعتين' : ' قطعة') : 'قريباً') + '</small></a>';
    }).join('');
    $$('a', r).forEach(function (a) {
      a.addEventListener('mouseenter', function () { var im = $('#catPv'); im.src = a.dataset.img; im.classList.add('on') });
      a.addEventListener('click', function () { closeCats() });
    });
  }
  // freeze the page behind an open panel: works on every phone browser (overflow:hidden alone does not on some)
  var LOCK_Y = 0, LOCKS = 0;
  function lockPage() { if (LOCKS++) return; LOCK_Y = scrollY; var b = document.body.style; document.documentElement.classList.add('plock'); b.position = 'fixed'; b.top = -LOCK_Y + 'px'; b.left = '0'; b.right = '0'; b.width = '100%' }
  function unlockPage() { if (!LOCKS) return; LOCKS = 0; var b = document.body.style; document.documentElement.classList.remove('plock'); b.position = b.top = b.left = b.right = b.width = ''; scrollTo(0, LOCK_Y) }
  document.addEventListener('touchmove', function (e) {   // a drag on the dimmed area, or inside a panel with nothing left to scroll, goes nowhere
    if (!LOCKS) return; var sc = e.target.closest && e.target.closest('.catp-in'); if (!sc || sc.scrollHeight <= sc.clientHeight + 1) e.preventDefault() }, { passive: false });
  function openCats(e) { if (e) e.preventDefault(); $('#mnav').classList.remove('open'); $('#catp').classList.add('open'); lockPage(); var f = $('#catRow a'); if (f) { $('#catPv').src = f.dataset.img; $('#catPv').classList.add('on') } }
  function closeCats() { $('#catp').classList.remove('open'); unlockPage() }
  $$('[data-cats]').forEach(function (b) { b.addEventListener('click', openCats) });
  $('#catX').onclick = closeCats; $('#catp').addEventListener('click', function (e) { if (e.target.id === 'catp') closeCats() });
  addEventListener('keydown', function (e) { if (e.key === 'Escape') closeCats() });
  function colItems(c) { return SITE.pieces.filter(c.f) }
  function renderHomeCols() {
    if (!$('#homeCols')) return;
    var used = {}, html = '';
    COLS.forEach(function (c, i) {
      var items = colItems(c); if (!items.length) return;
      var pick = items.filter(function (p) { return p.photo && !used[p.code] })[0] || items[0]; used[pick.code] = 1;
      html += '<a class="coll rv' + (i % 3 ? ' d' + (i % 3) : '') + '" href="#collection-' + c.key + '"><img src="' + esc(pick.photo) + '" alt="" loading="lazy"><span class="frame"></span><div class="in2"><div><div class="k2">' + ('0' + (i + 1)).slice(-2) + ' — ' + items.length + ' قطع</div><h3>' + c.t + '</h3></div><span class="go"><svg class="i"><use href="#s-arr"/></svg></span></div></a>';
    });
    $('#homeCols').innerHTML = html;
  }

  /* ---------- cards ---------- */
  function card(p, extra) {
    var fav = inList(p.code), g = (p.gallery && p.gallery.length ? p.gallery : [p.photo]).filter(Boolean), multi = g.length > 1;
    // all the piece's photos side by side: swipe them inside the card (or use the arrows), without opening the piece
    var strip = g.length ? '<div class="sw' + (multi ? ' multi' : '') + '">' + g.map(function (u) { return '<img loading="lazy" draggable="false" src="' + esc(u) + '" alt="' + esc(p.title) + '">' }).join('') + '</div>' : '';
    if (multi) strip += '<div class="dots">' + g.map(function (u, i) { return '<i' + (i ? '' : ' class="on"') + '></i>' }).join('') + '</div>' +
      '<button class="nv pv" dir="ltr" data-nv="-1" aria-label="الصورة السابقة">›</button><button class="nv nx" dir="ltr" data-nv="1" aria-label="الصورة التالية">‹</button>';
    return '<article class="card ' + (extra || '') + '" data-code="' + esc(p.code) + '"><div class="ph">' + strip +
      '<span class="tag">' + p.karat + 'K</span>' + (p.status === 'reserved' ? '<span class="tag l">محجوزة</span>' : p.is_new ? '<span class="tag l nw">وصل حديثاً</span>' : '') +
      '<button class="fav' + (fav ? ' on' : '') + '" data-fav="' + esc(p.code) + '" aria-label="اختياراتي"><svg class="i"><use href="#s-heart"/></svg></button><span class="qv">شاهد القطعة</span></div>' +
      '<div class="bd"><h3>' + esc(p.title) + '</h3><div class="m"><span class="num">' + p.weight.toFixed(2) + '</span> جم · عيار 21</div><div class="pr">' + moneyH(p.price) + '</div></div></article>';
  }
  function swipe(sw) {
    var ph = sw.parentNode, dots = $$('.dots i', ph), n = dots.length, t, down = null;
    var rtl = function () { return getComputedStyle(sw).direction === 'rtl' };
    var idx = function () { return Math.max(0, Math.min(n - 1, Math.round(Math.abs(sw.scrollLeft) / (sw.clientWidth || 1)))) };
    var go = function (k) { sw.scrollTo({ left: (rtl() ? -1 : 1) * k * sw.clientWidth, behavior: 'smooth' }) };
    sw.addEventListener('scroll', function () {
      clearTimeout(t);
      t = setTimeout(function () { var k = idx(); dots.forEach(function (d, j) { d.classList.toggle('on', j === k) }) }, 50);
    }, { passive: true });
    $$('[data-nv]', ph).forEach(function (b) { b.onclick = function (e) { e.preventDefault(); e.stopPropagation(); go(Math.max(0, Math.min(n - 1, idx() + Number(b.dataset.nv)))) } });
    // a mouse can drag the photos too (fingers scroll on their own); a drag never opens the piece
    sw.addEventListener('pointerdown', function (e) { if (e.pointerType === 'mouse' && !e.button) down = { x: e.clientX, l: sw.scrollLeft, moved: false } });
    sw.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - down.x;
      if (!down.moved && Math.abs(dx) > 6) { down.moved = true; sw.classList.add('drag'); try { sw.setPointerCapture(e.pointerId) } catch (x) {} }
      if (down.moved) sw.scrollLeft = down.l - dx;
    });
    var up = function () {
      if (!down) return;
      var moved = down.moved; down = null; sw.classList.remove('drag');
      if (moved) { sw.dataset.dragged = '1'; go(idx()); setTimeout(function () { delete sw.dataset.dragged }, 80) }
    };
    sw.addEventListener('pointerup', up); sw.addEventListener('pointercancel', up);
  }
  function bindCards(root, via) {
    $$('.sw.multi', root).forEach(swipe);
    $$('.card', root).forEach(function (c) { c.onclick = function (e) {
      if (e.target.closest('[data-fav]') || e.target.closest('[data-nv]')) return;
      var sw = e.target.closest('.sw'); if (sw && sw.dataset.dragged) return;
      if (via === 'ai') T('ai_detail_open', c.dataset.code, null, 1); location.hash = 'p-' + c.dataset.code } });
    $$('[data-fav]', root).forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); toggleList(b.dataset.fav, via); b.classList.toggle('on', inList(b.dataset.fav)) } });
  }
  function renderNew() {
    if (!$('#newRail')) return;
    var items = SITE.pieces.slice().sort(function (a, b) { return a.code < b.code ? 1 : -1 }).slice(0, 8);
    $('#newRail').innerHTML = items.map(function (p) { return card(p) }).join(''); bindCards($('#newRail'));
  }
  $$('[data-rail]').forEach(function (b) { b.onclick = function () { var r = $('#newRail'); r.scrollBy({ left: (+b.dataset.rail) * -r.clientWidth * .8, behavior: 'smooth' }) } });

  /* ---------- spotlight: piece of the week ---------- */
  function renderSpot() {
    if (!$('#spot')) return;
    var p = SITE.pieces.filter(function (x) { return x.style === 'فخم' && x.photo })[1] || SITE.pieces[0]; if (!p) return;
    $('#spot').innerHTML = '<div class="ph wipe" id="spotPh"><img src="' + esc(p.photo) + '" alt="' + esc(p.title) + '"></div><div><span class="eyebrow rv">قطعة الأسبوع</span><h2 class="ttl rv d1">' + esc(p.title) + '</h2><p class="lead rv d2">' + esc(p.description || '') + '</p>' +
      '<div class="meta2 rv d2"><div><small>الوزن</small><b class="num">' + p.weight.toFixed(2) + '</b> جم</div><div><small>العيار</small><b class="num">21K</b></div><div><small>الاستلام</small><b>' + ((SITE.branches || []).length === 1 ? 'من المحل' : 'من أي فرع') + '</b></div></div>' +
      '<div class="pr rv d3">' + moneyH(p.price) + '</div><div class="rv d3" style="display:flex;gap:12px;flex-wrap:wrap"><a class="btn g" href="#p-' + p.code + '">تفاصيل القطعة <svg class="i ar"><use href="#s-arr"/></svg></a><button class="btn" data-open-chat="أبغى أعرف أكثر عن ' + esc(p.title) + '">اسأل المستشار</button></div></div>';
    bindChatBtns($('#spot'));
  }

  /* ---------- collection page ---------- */
  var curCol = null, term = '', PB = 'all';
  function fmtShort(yer) { var v = conv(yer); return (v >= 1e6 ? (v / 1e6).toFixed(1).replace(/\.0$/, '') + ' مليون' : fmt(v)) + ' ' + curLbl() }
  function openFlt() { $('#fltp').classList.add('open'); lockPage() }
  function closeFlt() { $('#fltp').classList.remove('open'); unlockPage() }
  $('#fltBtn').onclick = openFlt; $('#fltX').onclick = closeFlt;
  $('#fltp').addEventListener('click', function (e) { if (e.target.id === 'fltp') closeFlt(); if (e.target.closest('#chips a')) closeFlt() });
  function renderCollection(key) {
    curCol = COLS.filter(function (c) { return c.key === key })[0] || null;
    var items = curCol ? colItems(curCol) : SITE.pieces;
    $('#colTitle').innerHTML = curCol ? esc(curCol.t) : 'كل <em>القطع</em>';
    $('#colCrumb').textContent = curCol ? curCol.t : 'المجموعات';
    $('#colLead').textContent = curCol ? curCol.s + ' — الأسعار على سعر الذهب اليوم.' : 'الأسعار على سعر الذهب اليوم.';
    $('#colBg').style.backgroundImage = '';   // no piece fills the screen here
    $('#chips').innerHTML = '<a class="chip' + (curCol ? '' : ' on') + '" href="#collections">الكل</a>' + COLS.filter(function (c) { return c.key.indexOf('cat-') === 0 && colItems(c).length }).map(function (c) { return '<a class="chip' + (curCol === c ? ' on' : '') + '" href="#collection-' + c.key + '">' + c.t + '<small style="color:var(--faint);font-size:12px">' + colItems(c).length + '</small></a>' }).join('');
    // price band and order: bands come from the real prices on display, so they always fit the stock
    var ps = SITE.pieces.map(function (p) { return p.price }).sort(function (a, b) { return a - b }), q1 = ps[Math.floor(ps.length / 3)] || 0, q2 = ps[Math.floor(ps.length * 2 / 3)] || 0;
    var bands = [['all', 'كل الأسعار'], ['lo', 'حتى ' + fmtShort(q1)], ['mid', fmtShort(q1) + ' – ' + fmtShort(q2)], ['hi', 'أكثر من ' + fmtShort(q2)]];
    $('#pband').innerHTML = bands.map(function (b) { return '<button class="chip' + (PB === b[0] ? ' on' : '') + '" data-b="' + b[0] + '">' + b[1] + '</button>' }).join('');
    $$('#pband [data-b]').forEach(function (b) { b.onclick = function () { PB = b.dataset.b; T('filter_price', null, PB); renderCollection(curCol ? curCol.key : ''); closeFlt() } });
    if (PB === 'lo') items = items.filter(function (p) { return p.price <= q1 });
    if (PB === 'mid') items = items.filter(function (p) { return p.price > q1 && p.price <= q2 });
    if (PB === 'hi') items = items.filter(function (p) { return p.price > q2 });
    var SORTS = [['new', 'الأحدث'], ['pa', 'السعر: من الأقل'], ['pd', 'السعر: من الأعلى'], ['wa', 'الوزن: الأخف'], ['wd', 'الوزن: الأثقل']];
    $('#sortl').innerHTML = SORTS.map(function (o) { return '<button class="chip' + ($('#sort').value === o[0] ? ' on' : '') + '" data-s="' + o[0] + '">' + o[1] + '</button>' }).join('');
    $$('#sortl [data-s]').forEach(function (b) { b.onclick = function () { $('#sort').value = b.dataset.s; T('filter_sort', null, b.dataset.s); renderCollection(curCol ? curCol.key : ''); closeFlt() } });
    var nf = (curCol ? 1 : 0) + (PB !== 'all' ? 1 : 0) + ($('#sort').value !== 'new' ? 1 : 0);
    $('#fltCnt').textContent = nf; $('#fltCnt').classList.toggle('hidden', !nf);
    var so = $('#sort').value; items = items.slice().sort(function (a, b) { return so === 'pa' ? a.price - b.price : so === 'pd' ? b.price - a.price : so === 'wa' ? a.weight - b.weight : so === 'wd' ? b.weight - a.weight : (a.code < b.code ? 1 : -1) });
    var t = term.trim(); if (t) items = items.filter(function (p) { return (p.title + ' ' + p.kind + ' ' + (p.style || '') + ' ' + (p.occasion || '')).indexOf(t) >= 0 });
    $('#grid').innerHTML = items.length ? items.map(function (p, i) { return card(p, 'rv' + (i % 4 ? ' d' + (i % 4) : '')) }).join('') : '<div class="empty" style="grid-column:1/-1">ما لقينا قطع بهذا البحث. اسأل المستشار يساعدك.</div>';
    bindCards($('#grid')); reveal();
  }
  var st; $('#q').addEventListener('input', function (e) { term = e.target.value; renderCollection(curCol ? curCol.key : ''); clearTimeout(st); st = setTimeout(function () { if (term.trim().length > 1) T('search', null, term.trim()) }, 1200) });

  /* ---------- piece page ---------- */
  var openCode = null;
  function renderPiece(code, via) {
    var base = BY[code]; if (!base) { $('#pieceWrap').innerHTML = '<div class="empty" style="margin:160px 0">هذه القطعة بيعت أو لم تعد متاحة. <a class="link" href="#collections">شاهد القطع المتوفرة</a></div>'; return }
    openCode = code; T('piece_view', code, null, via === 'ai');
    function draw(p) {
      var gal = (p.gallery && p.gallery.length ? p.gallery : (p.photos && p.photos.length ? p.photos : [p.photo]).filter(Boolean).map(function (u) { return { role: '', url: u } }));
      var photos = gal.map(function (g) { return g.url }), pct = SITE.deposit_pct || 10;
      var RL = {};   // no photo labels: every photo on the site is the shop's own studio photo
      var sim = SITE.pieces.filter(function (x) { return x.code !== p.code && (x.kind === p.kind || x.style === p.style) }).slice(0, 4);
      $('#pieceWrap').innerHTML = '<div class="pd"><div class="gal"><div class="main" id="gm" data-role="' + esc(gal[0] ? gal[0].role : '') + '"><img src="' + esc(photos[0] || '') + '" alt="' + esc(p.title) + '">' + (gal.length > 1 ? '<span class="gcnt" id="gcnt">1 / ' + gal.length + '</span>' : '') + '</div>' +
        (photos.length > 1 ? '<div class="th">' + gal.map(function (g, i) { return '<button' + (i ? '' : ' class="on"') + ' data-ph="' + esc(g.url) + '" data-i="' + i + '"><img src="' + esc(g.url) + '" alt="">' + (RL[g.role] ? '<small>' + RL[g.role] + '</small>' : '') + '</button>' }).join('') + '</div>' : '') + '</div>' +
        '<div class="pi"><div class="crumbs"><a href="#home">الرئيسية</a><span>/</span><a href="#collections">المجموعات</a><span>/</span><span>' + esc(p.kind) + '</span></div>' +
        '<h1>' + esc(p.title) + '</h1>' + (p.status === 'reserved' ? '<span class="avail" style="color:var(--warn)"><i></i>محجوزة حالياً</span>' : '<span class="avail"><i></i>متوفرة · ' + ((SITE.branches || []).length === 1 ? 'تستلمها من المحل' : 'تستلمها من الفرع اللي يريحك') + '</span>') +
        '<div class="specs"><div><small>الوزن</small><b class="num">' + p.weight.toFixed(2) + '</b> جم</div><div><small>العيار</small><b class="num">21K</b></div><div><small>رقم القطعة</small><b class="num">' + esc(p.code) + '</b></div></div>' +
        (p.description ? '<p class="desc">' + esc(p.description) + '</p>' : '') +
        '<div class="price">' + moneyH(p.price) + '</div><div class="pnote">' + (CUR === 'YER' ? 'تقريباً ' + esc(money(p.price, 'USD')) + ' · ' + esc(money(p.price, 'SAR')) : esc(money(p.price, 'YER'))) + '</div><div class="pnote2">على سعر ذهب اليوم، والسعر النهائي بسعر يوم الشراء</div>' +
        '<div class="acts">' + (p.status === 'available' ? '<button class="btn g" data-buy="full">اشترها بتحويل كامل</button><button class="btn btn2l" data-buy="deposit">احجزها بعربون ' + pct + '%<small>تنحفظ ' + (SITE.deposit_hours || 24) + ' ساعة، وما يثبت السعر</small></button>' : '') +
        '<button class="btn" data-fav2>' + (inList(p.code) ? 'في اختياراتي' : 'أضف لاختياراتي') + '</button><button class="btn" data-open-chat="أبغى أعرف أكثر عن ' + esc(p.title) + ' (' + p.code + ')"><svg class="b"><use href="#s-spark"/></svg>اسأل المستشار</button>' +
        '<a class="btn wide" href="#" data-ask><svg class="b"><use href="#s-wa"/></svg>استفسر عنها على واتساب</a><a class="btn wide" href="#" data-share>شاركها مع أحد</a></div></div></div>' +
        (sim.length ? '<section class="band" style="padding-top:20px"><div class="sh"><div><span class="eyebrow">تنسجم معها</span><h2 class="ttl">قطع <em>مشابهة</em></h2></div></div><div class="grid" id="simGrid">' + sim.map(function (x) { return card(x) }).join('') + '</div></section>' : '');
      var gi = 0;
      function showG(i) {
        if (!gal.length) return; gi = (i + gal.length) % gal.length; var g = gal[gi];
        $('#gm img').src = g.url; $('#gm').dataset.role = g.role || '';
        if ($('#gcnt')) $('#gcnt').textContent = (gi + 1) + ' / ' + gal.length;
        $$('[data-ph]').forEach(function (x) { x.classList.toggle('on', +x.dataset.i === gi) });
      }
      $$('[data-ph]').forEach(function (b) { b.onclick = function () { showG(+b.dataset.i) } });
      var gm = $('#gm'), sx = null, sy = 0, swiped = false;
      gm.addEventListener('touchstart', function (e) { var t = e.changedTouches[0]; sx = t.clientX; sy = t.clientY; swiped = false }, { passive: true });
      gm.addEventListener('touchend', function (e) {
        if (sx === null || gal.length < 2) return; var t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy; sx = null;
        if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
        swiped = true; var rtl = document.documentElement.dir !== 'ltr'; showG(gi + ((dx < 0) !== rtl ? 1 : -1));
      }, { passive: true });
      gm.onclick = function () { if (swiped) { swiped = false; return } gm.classList.toggle('zoom'); if (!gm.classList.contains('zoom')) $('#gm img').style.transform = '' };
      gm.onmousemove = function (e) { if (!gm.classList.contains('zoom')) return; var r = gm.getBoundingClientRect(); $('#gm img').style.transform = 'scale(2.2)'; $('#gm img').style.transformOrigin = ((e.clientX - r.left) / r.width * 100) + '% ' + ((e.clientY - r.top) / r.height * 100) + '%' };
      $$('[data-buy]').forEach(function (b) { b.onclick = function () { checkout(p, b.dataset.buy, via) } });
      $('[data-fav2]').onclick = function () { toggleList(p.code, via); this.textContent = inList(p.code) ? 'في اختياراتي' : 'أضف لاختياراتي' };
      $('[data-ask]').onclick = function (e) { e.preventDefault(); var u = wa('السلام عليكم، شدّتني القطعة «' + p.title + '» (رقم ' + p.code + ') في موقعكم، ويا ليت أعرف تفاصيل أكثر عنها.\n' + location.origin + '/p/' + p.code); T('whatsapp_click', p.code, 'piece'); if (u) window.open(u, '_blank', 'noopener'); else toast('رقم الواتساب يُضاف قريباً') };
      $('[data-share]').onclick = function (e) { e.preventDefault(); window.open('https://wa.me/?text=' + encodeURIComponent(p.title + ' — جمال المشرقي للذهب\n' + location.origin + location.pathname + '#p-' + p.code), '_blank', 'noopener') };
      bindChatBtns($('#pieceWrap')); var sg = $('#simGrid'); if (sg) bindCards(sg);
    }
    draw(base);
    if (ONLINE) fetch('/api/piece/' + encodeURIComponent(code)).then(function (r) { return r.ok ? r.json() : null }).then(function (d) { if (!d || d.code !== openCode) return; if (d.status === 'sold' || d.status === 'hidden' || d.status === 'inactive') { $('#pieceWrap').innerHTML = '<div class="empty" style="margin:160px 0">هذه القطعة بيعت أو لم تعد متاحة. <a class="link" href="#collections">شاهد القطع المتوفرة</a></div>'; return } draw(Object.assign({}, base, d)) }).catch(function () { });
  }

  /* ---------- bride builder ---------- */
  var BR = [], bKind = '';
  function renderBride() {
    var kinds = []; SITE.pieces.forEach(function (p) { if (kinds.indexOf(p.kind) < 0) kinds.push(p.kind) }); if (!bKind) bKind = kinds[0];
    $('#bSteps').innerHTML = kinds.map(function (k, i) { return '<button class="' + (k === bKind ? 'on' : '') + '" data-k="' + esc(k) + '">' + (i + 1) + ' · ' + esc(k) + '</button>' }).join('');
    $$('#bSteps button').forEach(function (b) { b.onclick = function () { bKind = b.dataset.k; renderBride() } });
    var items = SITE.pieces.filter(function (p) { return p.kind === bKind });
    $('#bGrid').innerHTML = items.map(function (p) { return '<article class="card' + (BR.indexOf(p.code) >= 0 ? ' sel' : '') + '" data-pick="' + p.code + '"><div class="ph"><img src="' + esc(p.photo || '') + '" alt=""><span class="chk"><svg class="i" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></span></div><div class="bd"><h3>' + esc(p.title) + '</h3><div class="pr">' + moneyH(p.price) + '</div></div></article>' }).join('');
    $$('[data-pick]').forEach(function (c) { c.onclick = function () { var k = c.dataset.pick, i = BR.indexOf(k); if (i >= 0) BR.splice(i, 1); else BR.push(k); renderBride() } });
    var picked = BR.map(function (c) { return BY[c] }).filter(Boolean), tot = picked.reduce(function (a, p) { return a + p.price }, 0);
    $('#bSum').innerHTML = '<h3>باقتك</h3>' + (picked.length ? picked.map(function (p) { return '<div class="li"><img src="' + esc(p.photo || '') + '" alt=""><div class="t">' + esc(p.title) + '</div><span class="num" style="color:var(--gold);font-size:14px">' + fmt(conv(p.price)) + '</span></div>' }).join('') : '<p style="color:var(--mut);font-size:14px">اختر القطع من اليمين وتظهر هنا.</p>') +
      '<div class="tot"><span>المجموع على سعر اليوم</span><b>' + moneyH(tot) + '</b></div><div style="display:grid;gap:10px"><a class="btn g full" href="#" id="bSend"' + (picked.length ? '' : ' style="opacity:.4;pointer-events:none"') + '><svg class="b"><use href="#s-wa"/></svg>أرسل الباقة على واتساب</a><button class="btn full" id="bList"' + (picked.length ? '' : ' disabled') + '>احفظها في اختياراتي</button><button class="btn full" data-open-chat="ساعدني أنسق باقة عروس">ساعدني أنسّق</button></div>';
    $('#bSend').onclick = function (e) { var u = wa('السلام عليكم، جهزت باقة عروس من الموقع: ' + picked.map(function (p) { return p.title + ' (' + p.code + ')' }).join('، ')); T('whatsapp_click', null, 'bride'); if (!u) { e.preventDefault(); toast('رقم الواتساب يُضاف قريباً') } else { this.href = u; this.target = '_blank' } };
    $('#bList').onclick = function () { BR.forEach(function (c) { if (!inList(c)) { LIST.push(c); T('shortlist_add', c, 'bride') } }); saveList(); toast('حُفظت الباقة في اختياراتي') };
    bindChatBtns($('#bSum'));
  }

  /* ---------- calculator: lives inside the price card (renderTicker) ---------- */

  /* ---------- the shop (one shop: a single card with address, hours, map and WhatsApp) ---------- */
  function renderBranches() {
    var one = SITE.branches.length === 1;
    if ($('#brEye')) { $('#brEye').textContent = one ? 'محلنا' : 'فروعنا'; $('#brTtl').innerHTML = one ? 'بجوار البوابة الرئيسية <em>لمركز جرعان</em>' : SITE.branches.length + ' فروع <em>في إب</em>' }
    if (one) {
      var b0 = SITE.branches[0], map0 = b0.map || 'https://maps.google.com/?q=' + encodeURIComponent('جمال المشرقي للذهب ' + b0.addr + (/إب/.test(b0.addr) ? '' : ' إب'));
      $('#brs').innerHTML = '<div class="g2s rv"><div class="g2s-row"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-6.5-7-11a7 7 0 0 1 14 0c0 4.5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg><div><b>' + esc(b0.n) + '</b><small>' + esc(b0.addr) + '</small></div></div>' +
        '<div class="g2s-row"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg><div><b>من 9 الصباح إلى 10 الليل</b></div></div>' +
        '<div class="g2s-act"><a class="btn" href="' + esc(map0) + '" target="_blank" rel="noopener">افتح الخريطة</a><a class="btn g" href="#" data-link="whatsapp">واتساب</a></div></div>';
      return;
    }
    $('#brs').innerHTML = SITE.branches.map(function (b, i) { var map = b.map || 'https://maps.google.com/?q=' + encodeURIComponent('جمال المشرقي للذهب ' + b.addr + (/إب/.test(b.addr) ? '' : ' إب')); return '<div class="br rv' + (i ? ' d' + i : '') + '">' + (one ? '' : '<span class="n num">0' + (i + 1) + '</span>') + '<h3>' + esc(b.n) + '</h3><p>' + (/إب/.test(b.addr) ? '' : 'إب — ') + esc(b.addr) + '</p><div class="r"><a class="btn s" href="' + esc(map) + '" target="_blank" rel="noopener">الخريطة</a><a class="btn g s" href="#" data-link="whatsapp">راسلنا</a></div></div>' }).join('');
  }

  /* ---------- shortlist ---------- */
  var LIST = []; try { LIST = JSON.parse(localStorage.getItem('gm_list') || '[]') } catch (e) { }
  function inList(c) { return LIST.indexOf(c) >= 0 }
  function saveList() { try { localStorage.setItem('gm_list', JSON.stringify(LIST)) } catch (e) { } var n = LIST.filter(function (c) { return BY[c] }).length; [$('#listCnt'), $('#mListCnt')].forEach(function (el) { el.textContent = n; el.classList.toggle('hidden', !n) }) }
  function toggleList(code, via) {
    if (inList(code)) { LIST.splice(LIST.indexOf(code), 1); T('shortlist_remove', code) }
    else { LIST.push(code); T('shortlist_add', code, null, via === 'ai'); if (via === 'ai') T('ai_add_shortlist', code, null, 1); toast('أُضيفت إلى اختياراتي') }
    saveList(); renderList(); $$('[data-fav="' + code + '"]').forEach(function (b) { b.classList.toggle('on', inList(code)) });
  }
  var X = '<svg class="i" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  function renderList() {
    var d = $('#drawer'); if (!d.classList.contains('open')) return;
    var items = LIST.map(function (c) { return BY[c] }).filter(Boolean), tot = items.reduce(function (a, p) { return a + p.price }, 0);
    d.innerHTML = '<div class="hd"><h3>اختياراتي</h3><button class="ibtn" data-close>' + X + '</button></div><div class="list">' +
      (items.length ? items.map(function (p) { return '<div class="li"><img src="' + esc(p.photo || '') + '" data-open="' + p.code + '" alt=""><div class="t"><b>' + esc(p.title) + '</b><span class="num">' + p.weight.toFixed(2) + ' جم</span></div><div class="p num">' + fmt(conv(p.price)) + '</div><button data-rm="' + p.code + '" aria-label="حذف" style="color:var(--faint)">' + X + '</button></div>' }).join('') : '<div class="empty" style="margin-top:20px">ما أضفت قطع بعد. اضغط على أي قطعة تعجبك.</div>') + '</div>' +
      (items.length ? '<div class="ft2"><div class="tot"><span>المجموع على سعر اليوم</span><b>' + moneyH(tot) + '</b></div><a class="btn g full" id="sendList" href="#"><svg class="b"><use href="#s-wa"/></svg>أرسل اختياراتي على واتساب</a></div>' : '');
    $$('[data-close]', d).forEach(function (b) { b.addEventListener('click', closeDrawer) });
    $$('[data-rm]', d).forEach(function (b) { b.onclick = function () { toggleList(b.dataset.rm) } });
    $$('[data-open]', d).forEach(function (b) { b.onclick = function () { closeDrawer(); location.hash = 'p-' + b.dataset.open } });
    var s = $('#sendList', d); if (s) s.onclick = function (e) { var u = wa('السلام عليكم، أبغى أستفسر عن هذي القطع: ' + items.map(function (p) { return p.title + ' (' + p.code + ')' }).join('، ')); T('whatsapp_click', null, 'shortlist'); if (!u) { e.preventDefault(); toast('رقم الواتساب يُضاف قريباً') } else { s.href = u; s.target = '_blank' } };
  }
  function openDrawer() { $('#drawer').classList.add('open'); $('#ov').classList.add('open'); renderList() }
  function closeDrawer() { $('#drawer').classList.remove('open'); if (!$('#modal').classList.contains('open')) $('#ov').classList.remove('open') }
  $('#listBtn').onclick = openDrawer; $('#mList').onclick = function (e) { e.preventDefault(); openDrawer() };
  $('#ov').onclick = function () { if ($('#modal').classList.contains('open')) return closeModal(); closeDrawer() };
  $('#menuBtn').onclick = function () { $('#mnav').classList.add('open') };
  $('#menuX').onclick = function () { $('#mnav').classList.remove('open') };
  $$('#mnav a').forEach(function (a) { a.addEventListener('click', function () { $('#mnav').classList.remove('open') }) });

  /* ---------- router: every section has its own address ---------- */
  var ROUTE = 'home';
  function route() {
    var h = decodeURIComponent(location.hash.replace('#', '')) || 'home', pg = 'home', arg = '';
    var pm = location.pathname.match(/^\/p\/([A-Za-z0-9]+)/); if (pm && !location.hash) { h = 'p-' + pm[1].toUpperCase() }
    if (h.indexOf('p-') === 0) { pg = 'piece'; arg = h.slice(2) }
    else if (h.indexOf('collection-') === 0) { pg = 'collections'; arg = h.slice(11) }
    else if (['collections', 'bride', 'gold'].indexOf(h) >= 0) pg = h;
    else if (h === 'branches' || h === 'home') pg = 'home';
    var changed = pg !== ROUTE || pg === 'piece' || pg === 'collections'; ROUTE = pg;
    $$('.page').forEach(function (p) { p.classList.toggle('on', p.id === 'pg-' + pg) });
    $$('#nav a').forEach(function (a) { a.classList.toggle('on', a.dataset.r === pg || (pg === 'piece' && a.dataset.r === 'collections')) });
    if (pg === 'collections') { renderCollection(arg); T('collection_open', null, arg || 'all') }
    if (pg === 'piece') renderPiece(arg.toUpperCase(), PENDING_VIA); PENDING_VIA = null;
    if (pg === 'bride') { renderBride(); T('bride_open') }
    if (pg === 'gold') renderTicker();
    if (changed) { if (h === 'branches') setTimeout(function () { $('#branches').scrollIntoView() }, 60); else window.scrollTo(0, 0) }
    T('page_view', null, pg); reveal(); scrollFx();
    if (pg === 'home' && window.ringRefresh) setTimeout(window.ringRefresh, 80);
  }
  var PENDING_VIA = null;
  window.openPiece = function (code, via) { PENDING_VIA = via; location.hash = 'p-' + code };
  addEventListener('hashchange', route);

  /* ---------- motion: header, reveals, parallax, cursor glow, magnetic buttons ---------- */
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } }) }, { threshold: .12 }) : null;
  function reveal() { $$('.page.on .rv:not(.in), .page.on .wipe:not(.in), footer .rv:not(.in)').forEach(function (e) { io ? io.observe(e) : e.classList.add('in') }) }
  var lastY = 0;
  var sprog = document.createElement('div'); sprog.className = 'sprog'; document.body.appendChild(sprog);
  function scrollFx() {
    var y = scrollY, hdr = $('#hdr');
    sprog.style.transform = 'scaleX(' + (y / Math.max(1, document.documentElement.scrollHeight - innerHeight)).toFixed(4) + ')';
    hdr.classList.toggle('solid', y > 40 || ROUTE !== 'home');
    hdr.classList.toggle('up', y > 400 && y > lastY + 4 && !$('#chat').classList.contains('open')); if (y < lastY - 4) hdr.classList.remove('up'); lastY = y;
    if (REDUCED || ROUTE !== 'home') return;
    var vh = innerHeight; hscFx(vh);
    // hero: the image sinks and dims as you leave
    var hr = $('#hero').getBoundingClientRect(), hp = clamp(-hr.top / vh, 0, 1);
    // spotlight + banner parallax
    var sp = $('#spotPh img'); if (sp) { var r = sp.parentNode.getBoundingClientRect(), t = (r.top + r.height / 2 - vh / 2) / vh; sp.style.transform = 'translate3d(0,' + (t * -8).toFixed(2) + '%,0) scale(1.04)' }
    var bb = null; if (bb) { var r2 = bb.parentNode.getBoundingClientRect(), t2 = (r2.top + r2.height / 2 - vh / 2) / vh; bb.style.transform = 'translate3d(0,' + (t2 * -10).toFixed(2) + '%,0) scale(1.08)' }
  }
  addEventListener('scroll', function () { requestAnimationFrame(scrollFx) }, { passive: true });
  if (!TOUCH && !REDUCED) {
    var g = $('#glow'), gx = 0, gy = 0, cx = 0, cy = 0;
    addEventListener('pointermove', function (e) { gx = e.clientX; gy = e.clientY; g.style.opacity = 1 });
    (function loop() { cx += (gx - cx) * .08; cy += (gy - cy) * .08; g.style.transform = 'translate(' + (cx - 260) + 'px,' + (cy - 260) + 'px)'; requestAnimationFrame(loop) })();
    document.addEventListener('pointermove', function (e) {
      var b = e.target.closest('.btn,.ibtn,.ai'); $$('.mag').forEach(function (x) { if (x !== b) { x.style.transform = ''; x.classList.remove('mag') } });
      if (b) { var r = b.getBoundingClientRect(); b.classList.add('mag'); b.style.transform = 'translate(' + ((e.clientX - r.left - r.width / 2) * .18).toFixed(1) + 'px,' + ((e.clientY - r.top - r.height / 2) * .25).toFixed(1) + 'px)' }
      var p = e.target.closest('[data-glow]'); if (p) { var r3 = p.getBoundingClientRect(); p.style.setProperty('--mx', (e.clientX - r3.left) + 'px'); p.style.setProperty('--my', (e.clientY - r3.top) + 'px') }
    });
  }
  function bindChatBtns(root) { $$('[data-open-chat]', root || document).forEach(function (b) { b.onclick = function (e) { e.preventDefault(); openChat(b.dataset.openChat || undefined) } }) }


  /* ---------- cinematic scene + pinned gallery ---------- */
  function renderScene() {
    var p = SITE.pieces.filter(function (x) { return x.photo && x.title.indexOf('كردان') >= 0 })[0] || SITE.pieces.filter(function (x) { return x.style === 'فخم' && x.photo })[0] || SITE.pieces[0]; if (!p) return;
    $('#sImg').src = p.photo; $('#sKind').textContent = p.kind + ' · ' + p.occasion; $('#sTitle').textContent = p.title;
    $('#sMeta').innerHTML = p.weight.toFixed(2) + ' جم · ' + moneyH(p.price);
    $('#sObj').onclick = function () { location.hash = 'p-' + p.code };
  }
  function renderHsc() {
    if (!$('#hTrack')) return;
    var items = SITE.pieces.filter(function (p) { return p.photo });
    $('#hTrack').innerHTML = items.map(function (p, i) { return '<a class="hit" href="#p-' + p.code + '"><span class="no num">' + ('0' + (i + 1)).slice(-2) + '</span><img src="' + esc(p.photo) + '" alt="' + esc(p.title) + '" loading="lazy"><div class="t"><small>' + esc(p.kind) + ' · ' + p.karat + 'K</small><b>' + esc(p.title) + '</b><span>' + moneyH(p.price) + '</span></div></a>' }).join('');
    $('#hCount').textContent = '01 / ' + ('0' + items.length).slice(-2);
  }
  function sceneFx(vh) {
    var sc = $('#scene'), r = sc.getBoundingClientRect(), len = r.height - vh; if (r.bottom < 0 || r.top > vh) return;
    var p = clamp(-r.top / len, 0, 1);
    var a = ease(clamp(p / .34, 0, 1)), b = ease(clamp((p - .3) / .3, 0, 1)), c = clamp((p - .62) / .38, 0, 1), cz = c * c * c;
    // 1) lying on the table, tilted → stands up frontal
    var rx = lerp(62, 0, a), rz = lerp(-24, 0, a), sc1 = lerp(.62, 1, a), ty = lerp(14, 0, a);
    // 2) turns to a side angle and rotates a little
    var ry = Math.sin(b * Math.PI) * -38 + b * 8, rz2 = Math.sin(b * Math.PI) * 4;
    // 3) the camera flies into it
    var zs = 1 + cz * 7.5;
    var sh = innerWidth >= 1000 ? ease(clamp((p - .34) / .12, 0, 1)) * (1 - ease(clamp((p - .6) / .1, 0, 1))) * 15 : 0;
    $('#sObj').style.transform = 'translate3d(' + sh.toFixed(2) + 'vw,' + ty + 'vh,0) rotateX(' + rx.toFixed(2) + 'deg) rotateY(' + ry.toFixed(2) + 'deg) rotateZ(' + (rz + rz2).toFixed(2) + 'deg) scale(' + (sc1 * zs).toFixed(3) + ')';
    $('#sObj').style.borderRadius = lerp(18, 0, c) + 'px';
    $('#sShine').style.transform = 'translateX(' + lerp(-60, 60, b) + '%)';
    $('#sShadow').style.opacity = (1 - c * 2) * a; $('#sShadow').style.transform = 'scaleX(' + lerp(1.3, .9, a) + ')';
    $('#sHalo').style.opacity = (a * (1 - c)).toFixed(3); $('#sHalo').style.transform = 'scale(' + lerp(.6, 1.2, b) + ')';
    $('#sCap1').style.opacity = (1 - clamp(p / .22, 0, 1)).toFixed(3); $('#sCap1').style.transform = 'translateY(' + (-p * 120) + 'px)';
    var c2 = clamp((p - .38) / .1, 0, 1) * (1 - clamp((p - .62) / .08, 0, 1));
    $('#sCap2').style.opacity = c2.toFixed(3); $('#sCap2').style.transform = 'translateY(' + lerp(30, 0, c2) + 'px)';
    $('#sIris').style.clipPath = 'circle(' + (clamp((p - .84) / .16, 0, 1) * 75).toFixed(1) + '% at 50% 50%)';
    $('#sProg').style.transform = 'scaleX(' + p.toFixed(3) + ')';
  }
  function hscFx(vh) {
    if (!$('#hsc')) return;
    var h = $('#hsc'), r = h.getBoundingClientRect(); if (r.bottom < 0 || r.top > vh) return;
    var tr = $('#hTrack'), max = tr.scrollWidth - innerWidth; if (max <= 0) return;
    var p = clamp(-r.top / (r.height - vh), 0, 1);
    tr.style.transform = 'translate3d(' + (p * max).toFixed(1) + 'px,0,0)';
    var its = $$('.hit', tr), mid = innerWidth / 2, n = 0;
    its.forEach(function (el, i) { var q = el.getBoundingClientRect(), d = (q.left + q.width / 2 - mid) / innerWidth; el.querySelector('img').style.transform = 'scale(1.08)'; var k = Math.min(1, Math.abs(d) * 1.6); el.style.transform = 'scale(' + (1 - k * 0.12).toFixed(3) + ')'; el.style.opacity = (1 - k * 0.45).toFixed(3); if (Math.abs(d) < .3) n = i });
    $('#hCount').textContent = ('0' + (n + 1)).slice(-2) + ' / ' + ('0' + its.length).slice(-2);
  }
  // discover: real pieces, editorial rhythm — one large, then pairs; name, weight and price under each photo
  function renderEd() {
    var g = $('#edGrid'); if (!g) return;
    var items = SITE.pieces.filter(function (p) { return p.photo }).slice().sort(function (a, b) { return a.code < b.code ? 1 : -1 }).slice(0, 7);
    g.innerHTML = items.map(function (p, i) {
      return '<a class="ei e' + (i + 1) + ' rv' + (i % 2 ? ' d1' : '') + '" href="#p-' + p.code + '"><span class="eim"><img loading="lazy" src="' + esc(p.photo) + '" alt="' + esc(p.title) + '"></span>' +
        '<span class="et"><b>' + esc(p.title) + '</b><small><span class="num">' + p.weight.toFixed(2) + '</span> جم · عيار 21</small><span class="ep">' + moneyH(p.price) + '</span></span></a>';
    }).join('');
    reveal();
  }
  // the shop: plain, quick, like any good store — tabs, cards, prices
  var STAB = 'all';
  function renderShop() {
    var g = $('#shopGrid'); if (!g) return;
    var cats = COLS.filter(function (c) { return c.key.indexOf('cat-') === 0 && colItems(c).length });
    $('#stabs').innerHTML = '<button class="' + (STAB === 'all' ? 'on' : '') + '" data-t="all">الكل</button>' + cats.map(function (c) { return '<button class="' + (STAB === c.key ? 'on' : '') + '" data-t="' + c.key + '">' + c.t + '</button>' }).join('');
    $$('#stabs [data-t]').forEach(function (b) { b.onclick = function () { STAB = b.dataset.t; T('shop_tab', null, STAB); renderShop() } });
    var col = COLS.filter(function (c) { return c.key === STAB })[0];
    var items = (col ? colItems(col) : SITE.pieces).slice().sort(function (a, b) { return a.code < b.code ? 1 : -1 }).slice(0, 8);
    g.innerHTML = items.map(function (p) { return card(p) }).join('') || '<div class="empty" style="grid-column:1/-1">لا توجد قطع في هذه الفئة الآن.</div>';
    bindCards(g);
  }
  function renderAll() { renderG2Hero(); renderShop(); renderCats(); renderCatTiles(); renderEd(); renderHsc(); renderTicker(); renderHomeCols(); renderNew(); renderSpot(); renderBranches(); saveList(); bindLinks(); bindChatBtns() }

  /* ---------- checkout: terms first, accounts after, receipt, review ---------- */
  var CK = null;
  function closeModal() {
    if (CK && CK.started && !CK.done) T('checkout_abandon', CK.p.code, 'step' + CK.step);
    CK = null; $('#modal').classList.remove('open');
    if (!$('#drawer').classList.contains('open')) $('#ov').classList.remove('open');
  }
  function checkout(p, kind, via) {
    CK = { p: p, kind: kind, step: 1, started: true, via: via }; T('checkout_start', p.code, kind, via === 'ai');
    $('#ov').classList.add('open'); $('#modal').classList.add('open'); ckDraw();
  }
  function ckDraw() {
    var m = $('#modal'), p = CK.p, pct = SITE.deposit_pct || 10, amt = CK.kind === 'full' ? p.price : Math.round(p.price * pct / 100);
    var steps = '<div class="stp">' + [1, 2, 3, 4].map(function (i) { return '<i' + (i <= CK.step ? ' class="on"' : '') + '></i>' }).join('') + '</div>';
    var hd = '<div class="hd"><h3>' + (CK.kind === 'full' ? 'شراء بتحويل كامل' : 'حجز بعربون') + '</h3><button class="ibtn" data-cx>' + X + '</button></div>';
    var body = '';
    if (CK.step === 1) {
      body = '<div class="choice"><button class="opt" data-k="full"><b>شراء بتحويل كامل المبلغ</b><span>السعر يثبت بسعر الذهب وقت التحويل، وتستلم القطعة من ' + ((SITE.branches || []).length === 1 ? 'المحل' : 'الفرع') + ' بعد تأكيد المحاسب.</span><span class="amt num">' + esc(money(p.price)) + '</span></button>' +
        '<button class="opt" data-k="deposit"><b>حجز بعربون ' + pct + '%</b><span>تُحفظ القطعة 24 ساعة بعد التأكيد، والسعر النهائي بسعر الذهب يوم الاستلام ويُخصم العربون.</span><span class="amt num">' + esc(money(Math.round(p.price * pct / 100))) + '</span></button></div>';
    } else if (CK.step === 2) {
      var txt = (SITE.policy || {})[CK.kind] || '';
      body = '<div class="note" style="margin:0 0 10px">اقرأ الشروط قبل أي تحويل. حسابات التحويل تظهر بعد موافقتك.</div><ul class="terms">' + txt.split(/[.؛]\s+/).filter(function (s) { return s.trim().length > 3 }).map(function (s) { return '<li>' + esc(s.replace(/\.$/, '')) + '.</li>' }).join('') + '</ul>' +
        '<label class="chkl"><input type="checkbox" id="agree"><span>قرأت الشروط وأوافق عليها، وأعرف أن الطلب لا يكون رسمياً إلا بعد مراجعة المحاسب للتحويل.</span></label><button class="btn g full" id="toAcc" disabled>موافق — اعرض حسابات التحويل</button><div class="err" id="ckErr"></div>';
    } else if (CK.step === 3) {
      var acc = CK.accounts || [];
      body = '<div class="pbox" style="margin-bottom:14px"><div class="big"><b class="num">' + esc(money(CK.amount, 'YER')) + '</b><span>' + (CK.kind === 'full' ? 'المبلغ الكامل' : 'مبلغ العربون') + '</span></div>' + (CUR !== 'YER' ? '<div class="alt">≈ ' + esc(money(CK.amount)) + '</div>' : '') + '</div>' +
        (acc.length ? acc.map(function (a) { return '<div class="acc"><div><b>' + esc(a.name) + '</b><span>' + esc(a.holder) + '</span></div><span class="num">' + esc(a.account) + '</span><button class="btn s" data-copy="' + esc(a.account) + '">نسخ</button></div>' }).join('')
          : '<div class="terms">' + (SITE.demo || !ONLINE ? 'هذه نسخة عرض؛ حسابات التحويل تُضاف من لوحة الإدارة.' : 'نرسل لك حساب التحويل على واتساب.') + '</div>') +
        '<div class="note">حوّل المبلغ ثم اضغط التالي لإرفاق صورة الإيصال.</div><button class="btn g full" id="toForm" style="margin-top:12px">حوّلت — التالي</button>';
    } else if (CK.step === 4) {
      body = '<label class="fld"><span>الاسم</span><input class="inp" id="fName" maxlength="80" autocomplete="name"></label><label class="fld"><span>رقم الجوال (واتساب)</span><input class="inp num" id="fPhone" maxlength="20" inputmode="tel" autocomplete="tel"></label>' +
        '<label class="fld"><span>' + (SITE.branches.length === 1 ? 'الاستلام من المحل' : 'من أي فرع يريحك تستلمها؟') + '</span><select class="inp" id="fPick">' + SITE.branches.map(function (b) { return '<option>' + esc(b.n + ' — ' + b.addr) + '</option>' }).join('') + '</select></label>' +
        '<label class="fld"><span>اسم المحوِّل كما في الإيصال</span><input class="inp" id="fPayer" maxlength="80"></label><label class="drop" id="drop"><input type="file" id="fRec" accept="image/*" hidden><span id="dropTx">اضغط لإرفاق صورة إيصال التحويل</span><img id="recPrev" class="hidden" alt=""></label>' +
        '<button class="btn g full" id="submit" style="margin-top:14px">أرسل الطلب للمراجعة</button><div class="err" id="ckErr"></div>';
    } else {
      body = '<div class="done"><div class="ok"><svg class="i" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div><h3 class="h" style="font-size:24px;margin:0 0 6px">وصل طلبك</h3><p style="color:var(--mut);margin:0 0 10px">رقم الطلب <b class="num">' + esc(CK.number || '') + '</b> — قيد المراجعة</p><p class="note">المحاسب يراجع التحويل ويتواصل معك. الطلب يصير رسمياً بعد التأكيد، والاستلام من ' + ((SITE.branches || []).length === 1 ? 'المحل' : 'الفرع') + ' بفاتورة رسمية.</p><button class="btn full" data-cx>تم</button></div>';
    }
    m.innerHTML = hd + '<div class="bd">' + steps + body + '</div>';
    $$('[data-cx]', m).forEach(function (b) { b.onclick = closeModal });
    $$('[data-k]', m).forEach(function (b) { b.onclick = function () { CK.kind = b.dataset.k; CK.step = 2; ckDraw() } });
    if (CK.step === 1) { CK.step = 1 }
    var ag = $('#agree', m); if (ag) ag.onchange = function () { $('#toAcc').disabled = !ag.checked };
    var ta = $('#toAcc', m); if (ta) ta.onclick = function () {
      T('terms_accept', p.code, CK.kind);
      if (!ONLINE) { CK.amount = amt; CK.accounts = [{"name": "بنك الكريمي", "holder": "جمال المشرقي للذهب والمجوهرات", "account": "0000 0000 0000"}, {"name": "النجم للحوالات", "holder": "جمال المشرقي للذهب والمجوهرات", "account": "000000000"}, {"name": "محفظة جيب", "holder": "جمال المشرقي", "account": "770 000 000"}, {"name": "محفظة ون كاش", "holder": "جمال المشرقي", "account": "770 000 000"}]; CK.step = 3; return ckDraw() }
      ta.disabled = true;
      fetch('/api/terms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: p.code, kind: CK.kind, accepted: true }) })
        .then(function (r) { return r.json().then(function (d) { if (!r.ok) throw d; return d }) })
        .then(function (d) { CK.token = d.token; CK.accounts = d.accounts; CK.amount = d.amount; CK.step = 3; ckDraw() })
        .catch(function (e) { ta.disabled = false; $('#ckErr').textContent = (e && e.error) || 'تعذر الاتصال' });
    };
    $$('[data-copy]', m).forEach(function (b) { b.onclick = function () { try { navigator.clipboard.writeText(b.dataset.copy); toast('تم النسخ') } catch (e) { } } });
    var tf = $('#toForm', m); if (tf) tf.onclick = function () { CK.step = 4; ckDraw() };
    var fr = $('#fRec', m); if (fr) fr.onchange = function () { var f = fr.files[0]; if (!f) return; shrink(f, function (url) { CK.receipt = url; $('#recPrev').src = url; $('#recPrev').classList.remove('hidden'); $('#dropTx').textContent = 'تم إرفاق الإيصال' }) };
    var sb = $('#submit', m); if (sb) sb.onclick = function () {
      var d = { code: p.code, kind: CK.kind, token: CK.token, name: $('#fName').value.trim(), phone: $('#fPhone').value.trim(), payer: $('#fPayer').value.trim(), pickup: ($('#fPick') || {}).value || '', receipt: CK.receipt, session: window.T.session };
      if (!d.name || d.phone.length < 7) return $('#ckErr').textContent = 'اكتب الاسم ورقم الجوال';
      if (!d.payer || !d.receipt) return $('#ckErr').textContent = 'اكتب اسم المحوِّل وأرفق صورة الإيصال';
      if (!ONLINE) { CK.number = 'DEMO'; CK.done = true; CK.step = 5; return ckDraw() }
      sb.disabled = true; sb.textContent = 'جاري الإرسال…';
      fetch('/api/request', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) })
        .then(function (r) { return r.json().then(function (x) { if (!r.ok) throw x; return x }) })
        .then(function (x) { T('request_submit', p.code, CK.kind, CK.via === 'ai'); CK.number = x.number; CK.done = true; CK.step = 5; ckDraw() })
        .catch(function (e) { sb.disabled = false; sb.textContent = 'أرسل الطلب للمراجعة'; $('#ckErr').textContent = (e && e.error) || 'تعذر الإرسال' });
    };
  }
  function shrink(file, cb) {
    var rd = new FileReader(); rd.onload = function () {
      var im = new Image(); im.onload = function () {
        var s = Math.min(1, 1600 / Math.max(im.width, im.height)), c = document.createElement('canvas');
        c.width = Math.round(im.width * s); c.height = Math.round(im.height * s); c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
        cb(c.toDataURL('image/jpeg', .85));
      }; im.onerror = function () { toast('الصورة غير صالحة') }; im.src = rd.result;
    }; rd.readAsDataURL(file);
  }
  $('#policyLink').onclick = function (e) {
    e.preventDefault(); var m = $('#modal'), P = SITE.policy || {};
    m.innerHTML = '<div class="hd"><h3>سياسة الحجز والشراء</h3><button class="ibtn" data-cx>' + X + '</button></div><div class="bd"><div class="grp">الحجز بعربون</div><div class="terms">' + esc(P.deposit) + '</div><div class="grp">الشراء بتحويل كامل</div><div class="terms">' + esc(P.full) + '</div></div>';
    $('[data-cx]', m).onclick = closeModal; m.classList.add('open'); $('#ov').classList.add('open');
  };


  /* ---------- assistant ---------- */
  var chatEl = $('#chat'), msgs = $('#msgs'), busy = false;
  function openChat(text) {
    chatEl.classList.add('open'); T('ai_open'); chatUsed = true; if (window.GM_vCheck) GM_vCheck(); hideHint(); document.body.classList.remove('has-hint'); if (innerWidth < 760) document.body.style.overflow = 'hidden';
    if (!msgs.children.length) { addMsg('حياك الله في جمال المشرقي أنا مستشارك الخاص، أعرف كل قطعة متوفرة وسعرها اليوم. تجهّز لمناسبة، ولا تدور على شيء معيّن؟', 'a'); chips(['أطقم العرايس', 'عقود', 'سعر الذهب اليوم', 'وين موقعكم؟']) }
    if (text) send(text); else setTimeout(function () { $('#chatIn').focus() }, 400);
  }
  window.openChat = openChat;
  $$('[data-open-chat]').forEach(function (b) { b.onclick = function (e) { e.preventDefault(); openChat() } });
  $('#chatX').onclick = function () { chatEl.classList.remove('open'); if (!openCode) document.body.style.overflow = ''; T('ai_close') };
  function addMsg(t, who) { var d = document.createElement('div'); d.className = 'mg ' + who; d.textContent = t; msgs.appendChild(d); msgs.scrollTop = 1e6; return d }
  function chips(list) {
    $('#sug').innerHTML = (list || []).map(function (s) { return '<button>' + esc(s) + '</button>' }).join('');
    $$('#sug button').forEach(function (b) { b.onclick = function () { T('ai_suggest_click', null, b.textContent, 1); send(b.textContent) } });
  }
  function cards(items) {
    if (!items || !items.length) return;
    var row = document.createElement('div'); row.className = 'pcs';
    row.innerHTML = items.map(function (p, i) {
      var photo = p.photo || (BY[p.code] || {}).photo || '';
      return '<div class="pc" style="animation-delay:' + (i * .12) + 's" data-code="' + esc(p.code) + '"><div class="im">' + (photo ? '<img src="' + esc(photo) + '" alt="">' : '') + '</div><div class="tx"><b>' + esc(p.title) + '</b><div class="mt num">' + p.karat + 'K · ' + Number(p.weight).toFixed(2) + ' جم</div><div class="pp">' + esc(money(p.price)) + '</div><div class="avl">' + (p.status === 'reserved' ? 'محجوزة حالياً' : ((SITE.branches || []).length === 1 ? 'متوفرة · الاستلام من المحل' : 'متوفرة · الاستلام من أي فرع')) + '</div><div class="row"><button data-d>التفاصيل</button><button data-l> أضف</button></div></div></div>';
    }).join('');
    msgs.appendChild(row); msgs.scrollTop = 1e6;
    items.forEach(function (p) { T('ai_card_shown', p.code, null, 1) });
    $$('.pc', row).forEach(function (c) {
      var code = c.dataset.code;
      c.onclick = function (e) {
        if (e.target.closest('[data-l]')) { toggleList(code, 'ai'); return }
        T('ai_card_click', code, e.target.closest('[data-d]') ? 'details' : (e.target.closest('.im') ? 'image' : 'card'), 1);
        chatEl.classList.remove('open'); document.body.style.overflow = ''; openPiece(code, 'ai');
      };
    });
  }
  // the closing moment: reserve / buy / WhatsApp, right inside the chat
  function offerCard(o) {
    var p = BY[o.code] || o, pct = SITE.deposit_pct || 10, el = document.createElement('div'); el.className = 'offer';
    el.innerHTML = '<div class="oh">' + (p.photo ? '<img src="' + esc(p.photo) + '" alt="">' : '') + '<div><b>' + esc(p.title) + '</b><span>' + moneyH(p.price) + '</span></div></div>' +
      '<button class="btn g full" data-k="deposit">احجزها بعربون ' + pct + '%</button><button class="btn full" data-k="full">اشترها بتحويل كامل · يثبت سعرها اليوم</button>' +
      '<a class="btn full wa2" target="_blank" rel="noopener"><svg class="b"><use href="#s-wa"/></svg>كلّم المبيعات على واتساب</a>';
    var a = el.querySelector('.wa2'); a.href = o.wa || wa('السلام عليكم، شدّتني القطعة «' + p.title + '» (رقم ' + o.code + ') في موقعكم، وأبغى مساعدة في شرائها.\n' + location.origin + '/p/' + o.code) || '#';
    a.onclick = function (e) { T('ai_handoff_click', o.code, 'offer', 1); if (a.getAttribute('href') === '#') { e.preventDefault(); toast('رقم الواتساب يُضاف قريباً') } };
    $$('[data-k]', el).forEach(function (b) { b.onclick = function () {
      var piece = BY[o.code] || Object.assign({}, o, { title: p.title }); T('ai_offer_click', o.code, b.dataset.k, 1);
      chatEl.classList.remove('open'); document.body.style.overflow = ''; openPiece(o.code, 'ai');
      setTimeout(function () { checkout(piece, b.dataset.k, 'ai') }, 650);
    } });
    msgs.appendChild(el); msgs.scrollTop = 1e6;
  }
  function send(t) {
    t = (t || '').trim(); if (!t || busy) return; busy = true;
    addMsg(t, 'u'); $('#chatIn').value = ''; chips([]); T('ai_message', null, null, 1);
    var ty = addMsg('', 'a'); ty.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
    var done = function (d) {
      var fix = function (u) { return u ? u.replace(/%7BBASE%7D/g, encodeURIComponent(location.origin)) : u };
      d.handoff = fix(d.handoff); if (d.offer) d.offer.wa = fix(d.offer.wa);
      // like a person typing: the reply arrives in short messages, one after another
      var parts = String(d.text || '…').split(/\n\s*\n/).map(function (x) { return x.trim() }).filter(Boolean);
      var i = 0;
      (function next() {
        if (i < parts.length) {
          if (i) { ty = addMsg('', 'a'); ty.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>' }
          setTimeout(function () { ty.remove(); addMsg(parts[i++], 'a'); next() }, i ? Math.min(1600, 350 + parts[i].length * 18) : 0);
          return;
        }
        busy = false; cards(d.pieces);
        if (d.handoff !== undefined) {
          var a = document.createElement('a'); a.className = 'handoff'; a.target = '_blank'; a.rel = 'noopener';
          a.innerHTML = '<svg class="b"><use href="#s-wa"/></svg>كلّم المبيعات على واتساب'; a.href = d.handoff || wa('السلام عليكم، أبغى أستفسر عن مجموعتكم') || '#';
          a.onclick = function (e) { T('ai_handoff_click', null, null, 1); if (a.getAttribute('href') === '#') { e.preventDefault(); toast('رقم الواتساب يُضاف قريباً') } };
          msgs.appendChild(a); msgs.scrollTop = 1e6;
        }
        if (d.offer) offerCard(d.offer);
        chips(d.suggest);
      })();
    };
    if (!ONLINE || !SITE.ai) { setTimeout(function () { done(localReply(t)) }, 700); return }
    fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session: CHAT_ID, visitor: (window.T && window.T.visitor) || '', message: t, picks: LIST.slice(0, 40) }) })
      .then(function (r) { return r.json() }).then(done).catch(function () { done(localReply(t)) });
  }
  $('#chatForm').onsubmit = function (e) { e.preventDefault(); send($('#chatIn').value) };

  /* ---------- voice salesman (GPT-Live) — the shop's staff only, until the owner approves it for customers ----------
     The call is paid by the second, so it only stays open while someone is talking: when the customer and the assistant
     are both quiet it closes, and a speech detector on the phone (free) opens it again the moment the customer speaks.
     Prices, pieces and rules come from the same assistant as the text chat, and its cards appear here. */
  var BUSY_V = 'المساعد الصوتي مشغول الحين، كمّل معي كتابة هنا أو كلم فريق المبيعات على الواتساب.';
  var V = { on: false, st: 'off', pc: null, dc: null, tr: null, call: null, mic: null, ac: null, an: null, vt: null, bt: null, speaking: false,
    aSpeaking: false, aT: null, pend: 0, quiet: 0, uText: '', uBub: null, aBub: null, left: 0, since: 0, closeMs: 2500,
    opening: false, ending: false, resume: false, rd: false, miss: 0, told: false, lab: false, asking: false, txT: null,
    vv: '', vlist: [], sb: 0, paused: false, pAt: 0, sbMs: 0 };
  var micBtn = $('#micBtn'), vdock = $('#vdock'), orbW = $('#vOrbW'), chatEl = $('#chat');
  var IOS = /iP(hone|ad|od)/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  // an iPhone plays a call quietly (or from the earpiece) while the microphone is on: the assistant plays through a
  // louder path there, and if no sound comes through it the plain one takes over again
  function vBoost(stream) {
    var au = $('#vAudio'); if (!IOS || !V.ac || !V.ac.createMediaStreamSource) return;
    try {
      if (V.bst) { try { V.bst.src.disconnect() } catch (e) { } }
      var src = V.ac.createMediaStreamSource(stream), g = V.ac.createGain(), cp = V.ac.createDynamicsCompressor(), an = V.ac.createAnalyser();
      g.gain.value = 2.4; cp.threshold.value = -12; cp.knee.value = 6; cp.ratio.value = 6; cp.attack.value = 0.003; cp.release.value = 0.2;
      an.fftSize = 512; src.connect(g); g.connect(cp); cp.connect(V.ac.destination); cp.connect(an);
      V.bst = { src: src, an: an, ok: false, wait: 0, buf: new Float32Array(512) }; au.muted = true;
      if (V.ac.state === 'suspended') V.ac.resume();
    } catch (e) { V.bst = null; au.muted = false }
  }
  function vBoostCheck() {
    var b = V.bst; if (!b || b.ok || !V.aSpeaking || !b.an.getFloatTimeDomainData) return;
    b.an.getFloatTimeDomainData(b.buf); for (var s = 0, i = 0; i < b.buf.length; i++) s += b.buf[i] * b.buf[i];
    if (Math.sqrt(s / b.buf.length) > 0.002) { b.ok = true; return }
    b.wait += 50; if (b.wait > 1500) { try { b.src.disconnect() } catch (e) { } V.bst = null; $('#vAudio').muted = false }
  }
  function vSet(st, txt) {
    V.st = st; if (!vdock) return; vdock.dataset.st = st;
    var el = $('#vTx'); if (!el || el.dataset.t === txt) return; el.dataset.t = txt;
    clearTimeout(V.txT); el.classList.add('sw');
    V.txT = setTimeout(function () { el.textContent = txt; el.classList.remove('sw') }, 150);
  }
  function vPost(path, body) { return fetch('/api/voice/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(function (r) { return r.json() }) }
  function vSend(o) { try { if (V.dc && V.dc.readyState === 'open') V.dc.send(JSON.stringify(o)) } catch (e) { } }
  function vCheck() {
    if (!micBtn || location.protocol.indexOf('http') !== 0 || !navigator.mediaDevices || !window.RTCPeerConnection) return;
    fetch('/api/voice/status?v=' + encodeURIComponent((window.T && window.T.visitor) || ''), { cache: 'no-store' })
      .then(function (r) { return r.json() }).then(function (d) {
        micBtn.hidden = !(d && d.on) && !V.on; V.lab = !!(d && d.lab); V.test = !!(d && d.test); if (d && d.close_after_ms) V.closeMs = d.close_after_ms;
        if (d && !d.on && d.lab && d.why && !V.whyTold && chatEl.classList.contains('open')) {   // staff: say why there is no microphone
          V.whyTold = true; addMsg('للفريق فقط: زر الصوت مخفي الحين، ' + ({ hidden: 'لأنه موقّف من لوحة الإدارة', off: 'لأن المساعد مطفي أو ما فيه مفتاح', monthly: 'لأن الحد الشهري خلص', daily: 'لأن حد الصوت اليومي خلص', customer: 'لأن حدك اليومي خلص' }[d.why] || d.why) + '.', 'a');
        }
        if (d && d.voices && d.voices.length) {
          V.vlist = d.voices; var mine = ''; try { mine = localStorage.getItem('gm_vv') || '' } catch (e) { }
          V.vv = V.vlist.some(function (x) { return x.id === mine }) ? mine : (d.voice || V.vlist[0].id); vVoicesUI();
        }
      }).catch(function () { });
  }
  // the customer's voice choice: three voices, each with its own name
  function vName() { for (var i = 0; i < V.vlist.length; i++) if (V.vlist[i].id === V.vv) return V.vlist[i]; return { name: 'المستشار', g: 'm' } }
  function vVoicesUI() {
    var box = $('#vVoices'), btn = $('#vVoiceBtn'); if (!box || !btn) return;
    btn.hidden = V.vlist.length < 2; box.textContent = '';
    V.vlist.forEach(function (x) {
      var b = document.createElement('button'), n = document.createElement('b'), sm = document.createElement('small');
      b.type = 'button'; b.dataset.v = x.id; b.className = x.id === V.vv ? 'on' : ''; b.setAttribute('aria-pressed', x.id === V.vv ? 'true' : 'false');
      n.textContent = x.name; sm.textContent = x.sub || ''; b.appendChild(n); b.appendChild(sm); box.appendChild(b);
    });
  }
  function vVoicesShow(on) { var box = $('#vVoices'), btn = $('#vVoiceBtn'); if (!box) return; box.hidden = !on; btn.setAttribute('aria-expanded', on ? 'true' : 'false') }
  function vPick(id) {
    vVoicesShow(false); if (!id || id === V.vv) return;
    V.vv = id; try { localStorage.setItem('gm_vv', id) } catch (e) { } vVoicesUI();
    if (V.on && (V.pc || V.call)) {                            // in a call: reconnect with the new voice (about a second)
      vClose('voice'); vSet('dial', 'يحوّل لصوت ' + vName().name + '…');
      setTimeout(function () { if (V.on && !V.pc) vOpen(true, true) }, 350);
    }
  }
  function vStart() {
    if (V.on || V.asking) { vStop('user'); return }
    if (!V.told) { V.told = true; addMsg('بيطلب منك المتصفح إذن المايكروفون عشان تكلمني بصوتك. اسمح له، وتكلم براحتك.', 'a') }
    V.asking = true; V.rd = false; vcShow(); vSet('dial', 'يتصل…');
    try { if (IOS && navigator.audioSession) navigator.audioSession.type = 'play-and-record' } catch (e) { }
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }).then(function (s) {
      var still = V.asking; V.asking = false;
      if (!still) { s.getTracks().forEach(function (t) { t.stop() }); return }          // ended while the phone was asking
      V.mic = s; V.on = true; V.miss = 0; micBtn.classList.add('on'); micBtn.setAttribute('aria-pressed', 'true');
      vVad(s); vOpen(false);
    }).catch(function () { V.asking = false; vcHide(); addMsg('ما قدرت أوصل للمايكروفون. تقدر تسمح له من إعدادات المتصفح، أو تكتب لي هنا وأنا أرد عليك.', 'a') });
  }
  // a speech detector on the phone: a quarter second of real voice (the speech band, well above the room's own noise)
  function vVad(stream) {
    var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    V.ac = new AC(); var an = V.ac.createAnalyser(); an.fftSize = 1024; an.smoothingTimeConstant = 0.15; V.an = an;
    V.ac.createMediaStreamSource(stream).connect(an);
    var bins = new Float32Array(an.frequencyBinCount), hz = V.ac.sampleRate / an.fftSize, lo = Math.max(1, Math.floor(300 / hz)), hi = Math.ceil(3400 / hz);
    var floor = 0, warm = 0, on = 0, off = 0;
    V.vt = setInterval(function () {
      if (V.ac.state === 'suspended') V.ac.resume();
      vBoostCheck();
      an.getFloatFrequencyData(bins); var band = 0, all = 0;
      for (var i = 1; i < bins.length; i++) { var p = Math.pow(10, bins[i] / 10); all += p; if (i >= lo && i <= hi) band += p }
      if (warm < 10) { floor = (floor * warm + band) / (warm + 1); warm++; return }      // half a second to learn the room
      floor = Math.max(floor, 1e-12);
      var voice = band > floor * 6 && band / (all || 1) > 0.6;
      if (!voice) floor = floor * 0.98 + band * 0.02;                                   // the room's noise, learned slowly
      if (voice) { on += 50; off = 0 } else { off += 50; if (off > 300) on = 0 }
      var was = V.speaking; V.speaking = on >= 250 || (was && off < 600);
      if (V.speaking && !was && V.on && !V.pc && !V.opening && !V.ending) vOpen(true);   // he speaks again: reopen at once
      vTick();
    }, 50);
  }
  function vSbMs() { return V.sbMs + (V.paused ? Date.now() - V.pAt : 0) }
  function vTick() {
    if (V.st !== 'live' && V.st !== 'rest') return;
    var now = Date.now();
    if (V.left && !V.ending && (now - V.since) / 1000 >= V.left - 6) { vEnd(); return }
    if (V.speaking || V.aSpeaking || V.pend) { V.quiet = 0; return }
    if (!V.quiet) V.quiet = now;
    if (now - V.quiet >= V.closeMs) vClose('quiet');           // quiet long enough: stop paying, the detector keeps listening for free
  }
  function vIce(pc, ms) { return new Promise(function (res) { if (pc.iceGatheringState === 'complete') return res(); var t = setTimeout(res, ms); pc.addEventListener('icegatheringstatechange', function () { if (pc.iceGatheringState === 'complete') { clearTimeout(t); res() } }) }) }
  function vOpen(resume, quietly) {
    if (V.opening || V.pc || !V.mic) return; var tr0 = V.mic.getAudioTracks()[0]; if (!tr0) return;
    var nm = vName();
    V.opening = true; V.ending = false; V.rd = !!resume;
    if (!quietly) vSet('dial', resume ? nm.name + (nm.g === 'f' ? ' ترجع تسمعك…' : ' يرجع يسمعك…') : 'يتصل…');
    var mine = tr0.clone(), pc = new RTCPeerConnection(), dc = pc.createDataChannel('oai-events');
    pc.addTrack(mine, new MediaStream([mine])); V.pc = pc; V.dc = dc; V.tr = mine;
    pc.ontrack = function (e) { var au = $('#vAudio'); au.srcObject = e.streams[0]; au.muted = false; au.play().catch(function () { }); vBoost(e.streams[0]) };
    dc.onmessage = function (e) { var m; try { m = JSON.parse(e.data) } catch (x) { return } vEvent(m) };
    pc.onconnectionstatechange = function () { if (pc.connectionState === 'failed' && V.pc === pc) vDrop('net') };
    pc.createOffer().then(function (o) { return pc.setLocalDescription(o) }).then(function () { return vIce(pc, 2500) }).then(function () {
      return vPost('open', { sdp: pc.localDescription.sdp, session: CHAT_ID, visitor: (window.T && window.T.visitor) || '', resume: !!resume, voice: V.vv || '' });
    }).then(function (d) {
      V.opening = false; if (V.pc !== pc) return;
      if (!d || !d.ok) { vDrop(d && d.why, d && d.say, d && d.detail); return }
      V.call = d.call; V.left = d.budget_s || 0; V.closeMs = d.close_after_ms || V.closeMs; V.resume = !!resume;
      V.sb = d.standby_s || 0; V.sbMs = 0; V.paused = false;
      return pc.setRemoteDescription({ type: 'answer', sdp: d.sdp });
    }).catch(function () { V.opening = false; if (V.pc === pc) vDrop('net') });
  }
  function vEvent(m) {
    var t = m.type;
    if (t === 'session.started') { V.since = Date.now(); V.quiet = V.resume ? Date.now() + 4000 : 0; vSet('live', 'أسمعك، تكلم'); voBurst(); clearInterval(V.bt); V.bt = setInterval(vBeat, 10000) }
    else if (t === 'session.paused') { if (!V.paused) { V.paused = true; V.pAt = Date.now() } if (V.st === 'live') vSet('rest', 'تكلّم متى ما حبيت، أنا معك') }
    else if (t === 'session.resumed') { if (V.paused) { V.sbMs += Date.now() - V.pAt; V.paused = false } if (V.st === 'rest' || V.st === 'live') vSet('live', 'أسمعك، تكلم') }
    else if (t === 'session.input_transcript.delta') { V.quiet = 0; if (V.st === 'rest') vSet('live', 'أسمعك، تكلم'); V.uText += m.delta || ''; if (!V.uBub) V.uBub = addMsg('', 'u'); V.uBub.textContent += m.delta || ''; V.aBub = null; msgs.scrollTop = 1e6 }
    else if (t === 'session.output_transcript.delta') {
      V.aSpeaking = true; V.quiet = 0; clearTimeout(V.aT); V.aT = setTimeout(function () { V.aSpeaking = false; if (V.st === 'live') vSet('live', 'أسمعك، تكلم') }, 1400);
      if (!V.aBub) V.aBub = addMsg('', 'a'); V.aBub.textContent += m.delta || ''; V.uBub = null; msgs.scrollTop = 1e6;
      if (!V.pend) { var nm = vName(); vSet('live', nm.name + (nm.g === 'f' ? ' ترد عليك…' : ' يرد عليك…')) }
    }
    else if (t === 'session.delegation.created') vDelegate(m.id || (m.delegation && m.delegation.id));
    else if (t === 'session.closed' && V.pc) vClose('server', m.usage || (m.message && m.message.usage) || null);
  }
  // GPT-Live asks for help: the shop's own assistant answers (same rules and checker), its cards show here
  function vDelegate(id) {
    V.pend++; vSet('live', 'لحظة أشوف لك…');
    setTimeout(function () {                                   // the customer's words reach us a moment after the request
      var text = V.uText.trim(); V.uText = '';
      vPost('delegate', { call: V.call, text: text, picks: LIST.slice(0, 40) }).then(function (d) {
        V.pend = Math.max(0, V.pend - 1);
        if (d.misheard) { V.miss++; if (V.miss >= 2) { d.say = 'ما فهمت عليك زين. ممكن تكتب لي طلبك هنا في المحادثة؟'; V.miss = 0 } } else V.miss = 0;
        vSend({ type: 'session.commentary.append', event_id: 'r' + Date.now(), delegation_id: id, content: d.say || '' });
        if (d.pieces && d.pieces.length) cards(d.pieces);
        if (d.offer) offerCard(d.offer);
        if (d.handoff !== undefined) vHandoff(d.handoff);
        if (d.left_s !== undefined) V.left = (Date.now() - V.since) / 1000 + d.left_s;
        if (d.stop) vEnd();
      }).catch(function () {
        V.pend = Math.max(0, V.pend - 1);
        vSend({ type: 'session.commentary.append', event_id: 'r' + Date.now(), delegation_id: id, content: 'صار عندي خلل بسيط، ممكن تعيد طلبك؟' });
      });
    }, 700);
  }
  function vHandoff(h) {
    var a = document.createElement('a'); a.className = 'handoff'; a.target = '_blank'; a.rel = 'noopener';
    a.innerHTML = '<svg class="b"><use href="#s-wa"/></svg>كلّم المبيعات على واتساب';
    a.href = (h ? String(h).replace(/%7BBASE%7D/g, encodeURIComponent(location.origin)) : '') || wa('السلام عليكم، أبغى أستفسر عن مجموعتكم') || '#';
    msgs.appendChild(a); msgs.scrollTop = 1e6;
  }
  function vBeat() { if (!V.call) return; vPost('beat', { call: V.call, standby_ms: vSbMs() }).then(function (d) { if (d && d.left_s !== undefined) V.left = (Date.now() - V.since) / 1000 + d.left_s }).catch(function () { }) }
  // close this call (the voice stays on: the detector reopens it when he speaks)
  function vClose(reason, usage0) {
    if (!V.pc) return; var pc = V.pc, dc = V.dc, call = V.call, tr = V.tr, sbms = vSbMs();
    V.pc = V.dc = V.tr = V.call = null; V.aSpeaking = false; V.pend = 0; V.quiet = 0; V.uBub = V.aBub = null; V.paused = false; V.sbMs = 0; clearInterval(V.bt);
    var fin = false, done = function (usage) { if (fin) return; fin = true; try { pc.close() } catch (e) { } try { tr.stop() } catch (e) { } if (call) vPost('close', { call: call, usage: usage || null, reason: reason, standby_ms: sbms }).catch(function () { }) };
    if (usage0 !== undefined) done(usage0);
    else if (reason === 'voice') { try { dc.send(JSON.stringify({ type: 'session.close' })) } catch (e) { } done(null) }
    else { try { dc.send(JSON.stringify({ type: 'session.close' })) } catch (e) { } dc.onmessage = function (e) { var m; try { m = JSON.parse(e.data) } catch (x) { return } if (m.type === 'session.closed') done(m.usage || (m.message && m.message.usage)) }; setTimeout(function () { done(null) }, 4000) }
    if (V.on && reason !== 'voice') vSet('idle', 'أول ما تتكلم، أرجع أسمعك');
  }
  function vDrop(why, say, detail) {
    var pc = V.pc; V.pc = V.dc = V.call = null; V.opening = false; try { pc && pc.close() } catch (e) { } try { V.tr && V.tr.stop() } catch (e) { } V.tr = null;
    if (why === 'net') { addMsg('الاتصال ضعيف شوي. جرب مرة ثانية، أو اكتب لي هنا وأنا أرد عليك.', 'a'); vStop('net'); return }
    var keep = V.lab || V.test;                                // testing: keep the microphone and say why
    vStop('limit'); if (why !== 'bad') { if (!keep) micBtn.hidden = true; if (!(keep && detail)) addMsg(say || BUSY_V, 'a') }
    if (keep && detail) addMsg('للتجربة: الصوت ما اشتغل، ' + detail + '.', 'a');
  }
  // the customer's budget is nearly spent: say it plainly (never "a limit was reached") and carry on in writing
  function vEnd() {
    if (V.ending) return; V.ending = true;
    vSend({ type: 'session.instructions.append', event_id: 'b' + Date.now(), delegation_id: null, content: 'قل الآن بالضبط وبهدوء: «' + BUSY_V + '» ثم اسكت.' });
    setTimeout(function () { vStop('budget'); micBtn.hidden = true; addMsg(BUSY_V, 'a') }, 7000);
  }
  function vStop(reason) {
    if (!V.on) { if (V.asking || (vdock && !vdock.hidden)) { V.asking = false; vcHide() } return }
    V.on = false; vClose(reason || 'end');
    clearInterval(V.vt); V.vt = null; try { V.ac && V.ac.close() } catch (e) { } V.ac = null; V.an = null; V.speaking = false;
    V.bst = null; $('#vAudio').muted = false; try { if (IOS && navigator.audioSession) navigator.audioSession.type = 'auto' } catch (e) { }
    if (V.mic) V.mic.getTracks().forEach(function (t) { t.stop() }); V.mic = null;
    micBtn.classList.remove('on'); micBtn.setAttribute('aria-pressed', 'false'); V.st = 'off'; vcHide();
  }

  /* ---------- the call stage: a liquid-gold orb (one small canvas, drawn on the phone) ----------
     It flies out of the microphone when the call starts, rings while connecting, swells softly with the customer's
     voice, sends out rings when the assistant speaks, shimmers while the shop's assistant looks for pieces, and rests
     dim while the call sleeps between sentences. */
  var VO = { on: false, raf: 0, c: null, S: 196, d: 1, ph: 0, last: 0, lvU: 0, lvA: 0, aRaw: 0, aMax: 0, aSpk: 0, hasLv: false,
    stT: 0, stBusy: false, b: .8, sc: .9, glow: .4, dial: 0, think: 0, rings: [], peak: 0, tb: null, odd: false, hideT: null,
    calm: !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) };
  function voSize() {
    var cv = $('#vOrb'); if (!cv) return; VO.c = VO.c || cv.getContext('2d');
    var w = cv.clientWidth || 196; VO.S = w; VO.d = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.round(w * VO.d); cv.height = Math.round(w * VO.d);
  }
  function voMic() {                                           // the customer's voice, 0..1 (the room's noise barely counts)
    var an = V.an; if (!an) return 0;
    if (!an.getFloatTimeDomainData) return V.speaking ? .5 : 0;
    if (!VO.tb || VO.tb.length !== an.fftSize) VO.tb = new Float32Array(an.fftSize);
    an.getFloatTimeDomainData(VO.tb);
    for (var s = 0, x = VO.tb, i = 0; i < x.length; i++) s += x[i] * x[i];
    var l = (20 * Math.log10(Math.sqrt(s / x.length) + 1e-9) + 54) / 34;
    l = l < 0 ? 0 : l > 1 ? 1 : l;
    return V.speaking ? l : l * .2;
  }
  function voOut(now, dt) {                                    // the assistant's voice, 0..1, from the call's own sound level
    var pc = V.pc;
    if (!pc) { VO.aRaw = 0; return 0 }
    if (now - VO.stT > 110 && !VO.stBusy && pc.getStats) {
      VO.stT = now; VO.stBusy = true;
      pc.getStats().then(function (r) {
        VO.stBusy = false;
        r.forEach(function (x) { if (x.type === 'inbound-rtp' && (x.kind || x.mediaType) === 'audio' && typeof x.audioLevel === 'number') { VO.hasLv = true; VO.aRaw = x.audioLevel; if (x.audioLevel > VO.aMax) VO.aMax = x.audioLevel } });
      }, function () { VO.stBusy = false });
    }
    if (V.aSpeaking) VO.aSpk += dt * 1000;
    if (VO.hasLv && (VO.aMax > .004 || VO.aSpk < 1600)) return Math.min(1, Math.sqrt(VO.aRaw) * 1.7);
    if (!V.aSpeaking) return 0;
    var t = now / 1000;                                        // a phone that gives no level: a calm speech-like rhythm
    return Math.max(0, .42 + .3 * Math.sin(t * 24) * Math.sin(t * 6.8 + 1) + .18 * Math.sin(t * 13.3 + 2)) * (.75 + .25 * Math.sin(t * 1.7));
  }
  function voBlob(c, cx, cy, R, ph, a, u, s) {
    c.beginPath();
    for (var i = 0; i <= 96; i++) {
      var th = i / 96 * 6.2832,
        r = R * (1 + a * Math.sin(2 * th + ph * 1.1) + a * .8 * Math.sin(3 * th - ph * 1.7 + 1.3)
          + (a * .5 + s * .07) * Math.sin(5 * th + ph * 2.9 + .4) + u * .04 * Math.sin(4 * th - ph * 2.3 + 2.1)
          + s * .035 * Math.sin(7 * th + ph * 4.1));
      if (i) c.lineTo(cx + r * Math.cos(th), cy + r * Math.sin(th)); else c.moveTo(cx + r, cy);
    }
    c.closePath();
  }
  function voSpot(c, x, y, r, rgb, al) {
    var g = c.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, 'rgba(' + rgb + ',' + al.toFixed(3) + ')'); g.addColorStop(1, 'rgba(' + rgb + ',0)');
    c.fillStyle = g; c.fillRect(x - r, y - r, r * 2, r * 2);
  }
  function voDraw(now) {
    var c = VO.c; if (!c) return;
    var dt = Math.min(.05, VO.last ? (now - VO.last) / 1000 : .016); VO.last = now;
    var ez = function (f) { return 1 - Math.pow(1 - f, dt * 60) };
    var st = V.st, dial = st === 'dial', idle = st === 'idle' || st === 'off' || st === 'rest';
    var u = voMic(), a = voOut(now, dt);
    VO.lvU += (u - VO.lvU) * ez(u > VO.lvU ? .3 : .07);
    VO.lvA += (a - VO.lvA) * ez(a > VO.lvA ? .35 : .09);
    var talk = V.aSpeaking || VO.lvA > .08;
    VO.b += ((st === 'rest' ? .62 : idle ? .5 : dial ? .8 : talk ? 1 : .9) - VO.b) * ez(.05);
    VO.sc += ((idle ? .82 : dial ? .9 : 1) + VO.lvU * .1 + VO.lvA * .07 - VO.sc) * ez(.12);
    VO.glow += ((idle ? .22 : .55) + VO.lvA * .9 + VO.lvU * .4 - VO.glow) * ez(.08);
    VO.dial += ((dial && !V.rd ? 1 : 0) - VO.dial) * ez(.08);
    VO.think += ((V.pend > 0 ? 1 : 0) - VO.think) * ez(.06);
    if (!VO.calm) VO.ph += dt * (.55 + VO.lvU * 1.4 + VO.lvA * 2 + VO.think * .8);
    if (!VO.calm && VO.lvA > .32 && now - VO.peak > 700 && VO.rings.length < 4) { VO.peak = now; VO.rings.push(now) }
    var S = VO.S, cx = S / 2, cy = S / 2, R = S * .27 * VO.sc, ph = VO.ph, b = VO.b, tm = VO.calm ? 0 : now / 1000;
    c.setTransform(VO.d, 0, 0, VO.d, 0, 0); c.clearRect(0, 0, S, S); c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
    var g = c.createRadialGradient(cx, cy, R * .8, cx, cy, R * 1.75);                     // the aura
    g.addColorStop(0, 'rgba(217,184,114,' + (.32 * VO.glow).toFixed(3) + ')'); g.addColorStop(1, 'rgba(217,184,114,0)');
    c.fillStyle = g; c.fillRect(0, 0, S, S);
    for (var i = VO.rings.length - 1; i >= 0; i--) {                                      // rings the assistant's voice sends out
      var age = (now - VO.rings[i]) / 1500;
      if (age >= 1 || age < 0) { VO.rings.splice(i, 1); continue }
      c.beginPath(); c.arc(cx, cy, R * (1.04 + age * .55), 0, 6.2832);
      c.strokeStyle = 'rgba(234,205,142,' + (.5 * (1 - age) * (1 - age)).toFixed(3) + ')'; c.lineWidth = 1.7 - age; c.stroke();
    }
    if (VO.dial > .02) {                                                                  // ringing while it connects
      c.beginPath(); c.arc(cx, cy, R * 1.24, 0, 6.2832); c.strokeStyle = 'rgba(217,184,114,' + (.14 * VO.dial).toFixed(3) + ')'; c.lineWidth = 1; c.stroke();
      c.beginPath(); c.arc(cx, cy, R * 1.24, tm * 4.2, tm * 4.2 + 1.15); c.lineCap = 'round';
      c.strokeStyle = 'rgba(242,216,152,' + (.9 * VO.dial).toFixed(3) + ')'; c.lineWidth = 2.2; c.stroke();
    }
    c.globalAlpha = .45 + .55 * b;                                                        // the orb
    voBlob(c, cx, cy, R, ph, idle ? .01 : .014, VO.lvU, VO.lvA);
    c.save(); c.clip();
    var gb = c.createRadialGradient(cx - R * .34, cy - R * .42, R * .06, cx + R * .05, cy + R * .08, R * 1.12);
    gb.addColorStop(0, '#fff4d2'); gb.addColorStop(.2, '#f2d68f'); gb.addColorStop(.52, '#cc9d4a'); gb.addColorStop(.8, '#8e6627'); gb.addColorStop(1, '#4a3311');
    c.fillStyle = gb; c.fillRect(cx - R * 1.3, cy - R * 1.3, R * 2.6, R * 2.6);
    c.globalCompositeOperation = 'screen';                                                // molten light moving inside
    voSpot(c, cx + R * .42 * Math.cos(ph * .9), cy + R * .36 * Math.sin(ph * 1.15 + 1), R * .78, '255,236,186', .42 * b);
    voSpot(c, cx + R * .5 * Math.cos(ph * .6 + 2.4), cy + R * .44 * Math.sin(ph * .8 + .3), R * .6, '255,214,128', .32 * b);
    c.globalCompositeOperation = 'multiply';
    voSpot(c, cx + R * .55 * Math.cos(ph * .7 + 4), cy + R * .5 * Math.sin(ph * .95 + 2), R * .85, '120,80,24', .5);
    c.globalCompositeOperation = 'source-over';
    var gr = c.createRadialGradient(cx, cy + R * .06, R * .6, cx, cy, R * 1.06);           // depth: a darker rim
    gr.addColorStop(0, 'rgba(36,22,6,0)'); gr.addColorStop(1, 'rgba(36,22,6,.6)');
    c.fillStyle = gr; c.fillRect(cx - R * 1.3, cy - R * 1.3, R * 2.6, R * 2.6);
    voSpot(c, cx + R * .22, cy + R * .66, R * .42, '255,206,120', .22);                  // warm light bounced from below
    if (VO.think > .02) {                                                                 // looking for pieces: a light sweeps across
      var x = cx + ((tm * .75) % 1 * 2.8 - 1.4) * R, gs = c.createLinearGradient(x - R * .45, cy - R, x + R * .45, cy + R);
      gs.addColorStop(0, 'rgba(255,248,225,0)'); gs.addColorStop(.5, 'rgba(255,248,225,' + (.38 * VO.think).toFixed(3) + ')'); gs.addColorStop(1, 'rgba(255,248,225,0)');
      c.fillStyle = gs; c.fillRect(cx - R * 1.3, cy - R * 1.3, R * 2.6, R * 2.6);
    }
    c.save(); c.translate(cx - R * .36, cy - R * .46); c.scale(1, .72); voSpot(c, 0, 0, R * .34, '255,255,246', .8 * b); c.restore();
    c.restore();
    c.strokeStyle = 'rgba(255,236,190,' + (.18 * b).toFixed(3) + ')'; c.lineWidth = 1; c.stroke();
    c.globalAlpha = 1;
  }
  function voLoop(now) {
    VO.raf = 0; if (!VO.on) return;
    var skip = VO.calm ? now - VO.last < 200 : ((V.st === 'idle' || V.st === 'rest') && VO.lvU < .05 && VO.lvA < .05 && (VO.odd = !VO.odd));   // resting: half the frames
    if (!skip) voDraw(now);
    VO.raf = requestAnimationFrame(voLoop);
  }
  function voStart() { if (VO.on) return; VO.on = true; VO.last = 0; VO.rings = []; VO.raf = requestAnimationFrame(voLoop) }
  function voStop() { VO.on = false; if (VO.raf) cancelAnimationFrame(VO.raf); VO.raf = 0 }
  function voBurst() { if (!VO.calm && window.performance) VO.rings.push(performance.now()); VO.sc = Math.min(1.12, VO.sc + .06) }
  function voFly() {                                           // from the orb's resting place to the microphone (transforms ignored)
    var m = micBtn.getBoundingClientRect(), d = vdock.getBoundingClientRect();
    if (!m.width) return 'scale(.5)';
    return 'translate(' + Math.round(m.left + m.width / 2 - d.left - d.width / 2) + 'px,' + Math.round(m.top + m.height / 2 - d.top - orbW.offsetHeight / 2) + 'px) scale(.24)';
  }
  function vcPad() {
    var gap = chatEl.getBoundingClientRect().bottom - msgs.getBoundingClientRect().bottom;
    msgs.style.setProperty('--vpad', Math.max(0, Math.round(vdock.offsetHeight - gap + 4)) + 'px');
  }
  function vcShow() {
    if (!vdock) return;
    clearTimeout(VO.hideT); vdock.hidden = false; vdock.classList.remove('in'); chatEl.classList.add('vc');
    voSize(); vcPad();
    orbW.style.transition = 'none'; orbW.style.opacity = '0'; orbW.style.transform = voFly();
    void orbW.offsetWidth;
    orbW.style.transition = orbW.style.transform = orbW.style.opacity = '';
    VO.sc = .6; VO.b = .7; vdock.classList.add('in'); voStart();
    setTimeout(function () { if (msgs.scrollTo) msgs.scrollTo({ top: msgs.scrollHeight, behavior: 'smooth' }); else msgs.scrollTop = 1e6 }, 30);
  }
  function vcHide() {
    if (!vdock || vdock.hidden) return;
    clearTimeout(VO.hideT); vVoicesShow(false);
    orbW.style.transition = 'transform .42s cubic-bezier(.55,0,.75,.2),opacity .36s ease-in';
    orbW.style.transform = voFly(); orbW.style.opacity = '0';
    vdock.classList.remove('in'); chatEl.classList.remove('vc');
    VO.hideT = setTimeout(function () { vdock.hidden = true; orbW.style.transition = orbW.style.transform = orbW.style.opacity = ''; voStop() }, 460);
  }
  window.GM_vCheck = vCheck;
  if (micBtn) {
    micBtn.onclick = vStart; $('#vStop').onclick = function () { vStop('user') };
    $('#vVoiceBtn').onclick = function () { vVoicesShow($('#vVoices').hidden) };
    $('#vVoices').onclick = function (e) { var b = e.target.closest('button[data-v]'); if (b) vPick(b.dataset.v) };
    $('#chatX').addEventListener('click', function () { vStop('closed') });
    addEventListener('pagehide', function () { if (V.call) { try { navigator.sendBeacon('/api/voice/close', JSON.stringify({ call: V.call, reason: 'leave', standby_ms: vSbMs() })) } catch (e) { } } });
    document.addEventListener('visibilitychange', function () { if (document.hidden && (V.on || V.asking)) vStop('hidden') });
    addEventListener('resize', function () { if (VO.on && vdock && !vdock.hidden) { voSize(); vcPad() } });
    vCheck();
  }
  // offline / assistant-off replies: honest and helpful, never invented
  function localReply(t) {
    var p = SITE.prices, has = function (w) { return w.some(function (x) { return t.indexOf(x) >= 0 }) };
    if (has(['سعر', 'جرام', 'الذهب اليوم']) && p) return { text: 'سعر جرام عيار 21 اليوم: بيع ' + fmt(p.k21.sell) + ' — شراء ' + fmt(p.k21.buy) + ' ريال.\nالجنيه: بيع ' + fmt(p.pound.sell) + ' — شراء ' + fmt(p.pound.buy) + '.', suggest: ['أطقم العرايس', 'عقود'] };
    if (has(['فرع', 'فروع', 'وين', 'موقع'])) return { text: SITE.branches.map(function (b) { return '• ' + b.n + ': ' + b.addr }).join('\n'), suggest: ['أطقم العرايس'] };
    if (has(['طقم', 'عروس', 'عرس'])) return { text: 'هذي من الأطقم المتوفرة الآن:', pieces: SITE.pieces.filter(function (x) { return x.kind === 'طقم' }).slice(0, 3), suggest: ['عندكم أخف وزن؟', 'أبغى أكلم المبيعات'] };
    if (has(['عقد', 'كردان', 'قلاد'])) return { text: 'هذي من العقود المتوفرة:', pieces: SITE.pieces.filter(function (x) { return x.kind === 'عقد' }).slice(0, 3), suggest: ['أطقم العرايس'] };
    if (has(['احجز', 'اشتري', 'تحويل', 'خصم', 'المبيعات', 'أكلم'])) return { text: 'أكيد، فريق المبيعات يكمل معك التفاصيل على واتساب مباشرة.', handoff: '' };
    return { text: 'تقدر تسألني عن الأطقم والعقود، أو سعر الذهب اليوم، أو الفروع. ولو تحب تكلم فريق المبيعات مباشرة أوصلك فيهم.', suggest: ['أطقم العرايس', 'سعر الذهب اليوم'] };
  }

  /* ---------- assistant hint: short messages popping from the button, rotating, then quiet ---------- */
  var HINTS = [
    { t: 'وصلتنا قطع جديدة هالأسبوع، تبغى أوريك أحلاها؟', q: 'وش أحدث القطع اللي وصلتكم؟' },
    { t: 'خلني أطلع لك أقوى التشكيلات اللي عندنا الحين', q: 'وريني أفخم التشكيلات عندكم' },
    { t: 'تجهّز لعرس؟ أرتب لك طقم متكامل على ذوقك', q: 'أبغى أجهز طقم عروس' },
    { t: 'قل لي المناسبة والميزانية، وأرشّح لك الأنسب', q: '' },
    { t: 'محتار بين قطعتين؟ أقارن لك بينهم بصراحة', q: 'أبغى أقارن بين قطعتين' },
    { t: 'تبي تعرف كم سعر قطعة على ذهب اليوم؟ اسألني', q: '' }], hintN = 0, chatUsed = false, hintHide;
  function pieceHint() { var p = openCode && BY[openCode]; return p && ROUTE === 'piece' ? { t: 'تبغى أشرح لك تفاصيل «' + p.title + '» ووش يميزها؟', q: 'اشرح لي تفاصيل ' + p.title + ' (' + p.code + ')' } : null }
  function hint() {
    if (chatUsed || chatEl.classList.contains('open') || $('#modal').classList.contains('open') || hintN >= HINTS.length) return;
    if (hintN === 0) HINTS.sort(function () { return Math.random() - .5 }); var h = pieceHint() || HINTS[hintN]; hintN++; $('#aibTx').textContent = window.GM_tr ? GM_tr(h.t) : h.t; $('#aib').dataset.q = window.GM_tr ? GM_tr(h.q) : h.q;
    $('#aib').classList.add('on'); document.body.classList.add('has-hint');
    clearTimeout(hintHide); hintHide = setTimeout(hideHint, 6500);
  }
  function hideHint() { $('#aib').classList.remove('on') }
  $('#aib').onclick = function () { var q = this.dataset.q; hideHint(); openChat(q || undefined) };
  // on phones a hint covers the page, so only two gentle ones per visit
  (matchMedia('(max-width: 760px)').matches ? [12000, 60000] : [7000, 28000, 55000, 90000, 140000]).forEach(function (ms) { setTimeout(hint, ms) });


  /* ---------- live stock: a piece sold in any branch leaves this page within seconds ---------- */
  var AV = '';
  function syncStock() {
    if (!ONLINE || document.hidden) return;
    fetch('/api/avail', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null }).then(function (d) {
      if (!d || d.v === AV) return; var first = !AV; AV = d.v;
      var live = {}; d.available.forEach(function (c) { live[c] = 'available' }); d.reserved.forEach(function (c) { live[c] = 'reserved' });
      var before = SITE.pieces.length, changed = false;
      SITE.pieces = SITE.pieces.filter(function (p) { if (!live[p.code]) { changed = true; return false } if (p.status !== live[p.code]) { p.status = live[p.code]; changed = true } return true });
      if (first && !changed) return;
      BY = {}; SITE.pieces.forEach(function (p) { BY[p.code] = p });
      if (changed) { renderAll(); if (ROUTE === 'collections' || ROUTE === 'piece' || ROUTE === 'bride') route() }
    }).catch(function () { /* offline for a moment: keep what we have, try again next round */ });
  }
  setInterval(syncStock, 20000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) syncStock() });
  addEventListener('online', syncStock);

  /* ---------- boot ---------- */
  function boot() {
    BY = {}; SITE.pieces.forEach(function (p) { BY[p.code] = p });
    $$('#cur button').forEach(function (b) { b.classList.toggle('on', b.dataset.c === CUR) });
    renderHero(); renderAll();
    // the one piece that may fill the whole screen: the flower set with the belt, in the middle of the page
    var bp = SITE.pieces.filter(function (p) { return p.photo && (p.title.indexOf('الوردة') >= 0 || p.title.indexOf('الحزام') >= 0) })[0] || SITE.pieces.filter(function (p) { return p.kind === 'طقم' && p.photo && p.style === 'فخم' }).pop() || SITE.pieces[0];
    if (bp) { $('#brideBg').style.backgroundImage = "url('" + bp.photo + "')"; $('#brideHeadBg').style.backgroundImage = "url('" + bp.photo + "')" }
    $('#yr').textContent = new Date().getFullYear(); route();
    window.GM_SITE = SITE; window.GM_money = moneyH; document.dispatchEvent(new Event('gm:ready'));
  }
  (ONLINE ? fetch('/api/site').then(function (r) { if (!r.ok) throw 0; return r.json() }) : Promise.reject())
    .then(function (d) { if (d && d.v === 2) SITE = d; else throw 0 }).catch(function () { ONLINE = false; window.GM_OFFLINE = true }).then(boot);
  var t0 = Date.now(), qs = new URLSearchParams(location.search);
  addEventListener('load', function () { setTimeout(hideSplash, qs.get('nosplash') ? 0 : Math.max(0, 1200 - (Date.now() - t0))) });
})();

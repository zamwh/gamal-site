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
    branches: [{ n: 'الفرع الأول', addr: 'مركز جرعان — المحل رقم 6' }, { n: 'الفرع الثاني', addr: 'خط السبل — مركز وان مول، الدور الأول، المحل رقم 3' }, { n: 'الفرع الثالث', addr: 'بجوار البوابة الرئيسية لمركز جرعان' }],
    policy: { deposit: 'الحجز بعربون 10% من قيمة القطعة يحفظها 24 ساعة من تأكيده ولا يثبّت سعر الذهب؛ السعر النهائي بسعر الذهب يوم إتمام البيع ويُخصم منه العربون. لا يُعد الحجز مؤكداً إلا بعد مراجعة المحاسب لوصول التحويل. الاستلام في الفرع فقط بفاتورة موقعة من الطرفين.', full: 'شراء بتحويل كامل قيمة القطعة: يثبت السعر بسعر الذهب وقت التحويل، ولا يُعد الشراء رسمياً إلا بعد مراجعة المحاسب لوصول المبلغ كاملاً. بعد التأكيد تستلم القطعة من الفرع بفاتورة رسمية موقعة من الطرفين.' },
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

  /* ---------- theme: dark by default ---------- */
  var mode = 'night'; try { mode = localStorage.getItem('gm_mode3') || 'night' } catch (e) { }
  function applyMode() { document.documentElement.classList.toggle('day', mode === 'day'); $('meta[name=theme-color]').content = mode === 'day' ? '#f5f0e6' : '#070605' }
  $('#modeBtn').onclick = function () { mode = mode === 'day' ? 'night' : 'day'; try { localStorage.setItem('gm_mode3', mode) } catch (e) { } applyMode() };
  applyMode();

  var tt; function toast(m) { var t = $('#toast'); t.textContent = m; t.classList.add('on'); clearTimeout(tt); tt = setTimeout(function () { t.classList.remove('on') }, 2600) }
  function wa(text) { var n = String((SITE.links || {}).whatsapp || '').replace(/\D/g, ''); return n ? 'https://wa.me/' + n + (text ? '?text=' + encodeURIComponent(text) : '') : '' }
  function bindLinks() {
    $$('[data-link]').forEach(function (a) {
      var k = a.dataset.link, u = k === 'whatsapp' ? wa('السلام عليكم، تواصلت معكم من الموقع') : (SITE.links || {})[k];
      if (u) { a.href = u; a.target = '_blank'; a.rel = 'noopener' }
      a.onclick = function (e) { if (!u) { e.preventDefault(); toast('الرابط يُضاف قريباً') } T(k === 'whatsapp' ? 'whatsapp_click' : 'social_click', null, k) };
    });
  }

  /* ---------- price ribbon & quotes ---------- */
  function renderTicker() {
    var p = SITE.prices; if (!p) return;
    function it(l, o) { return '<div class="tk"><span>' + l + '</span><i>بيع</i><b class="num">' + fmt(conv(o.sell)) + '</b><i>' + curLbl() + '</i><i>شراء</i><span class="num">' + fmt(conv(o.buy)) + '</span>' + (o.chg ? '<span class="chg">' + (o.chg > 0 ? '▲ ' : '▼ ') + fmt(Math.abs(o.chg)) + '</span>' : '') + '</div><div class="tk"><span class="dia"></span></div>' }
    var one = it('جرام عيار 21', p.k21) + it('الجنيه الذهب', p.pound);
    $('#track').innerHTML = one + one + one + one;
    $('#hp21').innerHTML = moneyH(p.k21.sell); $('#hpP').innerHTML = moneyH(p.pound.sell);
    var q = function (l, o) { return '<div class="q"><small>' + l + (o.chg ? ' · <span class="chg">' + (o.chg > 0 ? '▲ ' : '▼ ') + fmt(Math.abs(o.chg)) + ' عن أمس</span>' : '') + '</small><div class="sell"><span class="lb">بيع</span>' + moneyH(o.sell) + '</div><div class="buy">شراء <b class="num">' + fmt(conv(o.buy)) + '</b> ' + curLbl() + '</div></div>' };
    var html = q('جرام عيار 21', p.k21) + q('الجنيه الذهب', p.pound);
    $('#quotesHome').innerHTML = html; $('#quotesGold').innerHTML = html;
    if (p.updated) { $('#upd').textContent = 'آخر تحديث ' + p.updated.slice(0, 16); $('#upd2').textContent = 'أسعار المحل — آخر تحديث ' + p.updated.slice(0, 16) }
    spark($('#sparkHome')); spark($('#sparkGold'));
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
    h.addEventListener('click', function (e) { if (moved || e.target.closest('a,button,.live,.sctl')) return; var p = HL[hi]; if (p) location.hash = 'p-' + p.code });
  })();

  /* ---------- collections ---------- */
  var COLS = [
    { key: 'bridal', t: 'أطقم العرايس', s: 'العقد والحلق والكف والحزام', f: function (p) { return p.kind === 'طقم' } },
    { key: 'necklaces', t: 'العقود والكردانات', s: 'صدر · مجدول · كردان', f: function (p) { return p.kind === 'عقد' } },
    { key: 'grand', t: 'الفخامة الكاملة', s: 'قطع تخطف الأنظار', f: function (p) { return p.style === 'فخم' } },
    { key: 'classic', t: 'الكلاسيكيات', s: 'أناقة هادئة لا تغيب', f: function (p) { return p.style === 'كلاسيكي' } },
    { key: 'engagement', t: 'للخطوبة', s: 'قطع أخف وأنعم', f: function (p) { return p.occasion === 'خطوبة' } }];
  function colItems(c) { return SITE.pieces.filter(c.f) }
  function renderHomeCols() {
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
    var fav = inList(p.code);
    return '<article class="card ' + (extra || '') + '" data-code="' + esc(p.code) + '"><div class="ph">' + (p.photo ? '<img loading="lazy" src="' + esc(p.photo) + '" alt="' + esc(p.title) + '">' : '') +
      '<span class="tag">' + p.karat + 'K</span>' + (p.status === 'reserved' ? '<span class="tag l">محجوزة</span>' : '') +
      '<button class="fav' + (fav ? ' on' : '') + '" data-fav="' + esc(p.code) + '" aria-label="اختياراتي"><svg class="i"><use href="#s-heart"/></svg></button><span class="qv">شاهد القطعة</span></div>' +
      '<div class="bd"><h3>' + esc(p.title) + '</h3><div class="m"><span class="num">' + p.weight.toFixed(2) + '</span> جم · ' + esc(p.branch) + '</div><div class="pr">' + moneyH(p.price) + '</div></div></article>';
  }
  function bindCards(root, via) {
    $$('.card', root).forEach(function (c) { c.onclick = function (e) { if (e.target.closest('[data-fav]')) return; if (via === 'ai') T('ai_detail_open', c.dataset.code, null, 1); location.hash = 'p-' + c.dataset.code } });
    $$('[data-fav]', root).forEach(function (b) { b.onclick = function (e) { e.stopPropagation(); toggleList(b.dataset.fav, via); b.classList.toggle('on', inList(b.dataset.fav)) } });
  }
  function renderNew() {
    var items = SITE.pieces.slice().sort(function (a, b) { return a.code < b.code ? 1 : -1 }).slice(0, 8);
    $('#newRail').innerHTML = items.map(function (p) { return card(p) }).join(''); bindCards($('#newRail'));
  }
  $$('[data-rail]').forEach(function (b) { b.onclick = function () { var r = $('#newRail'); r.scrollBy({ left: (+b.dataset.rail) * -r.clientWidth * .8, behavior: 'smooth' }) } });

  /* ---------- spotlight: piece of the week ---------- */
  function renderSpot() {
    var p = SITE.pieces.filter(function (x) { return x.style === 'فخم' && x.photo })[1] || SITE.pieces[0]; if (!p) return;
    $('#spot').innerHTML = '<div class="ph wipe" id="spotPh"><img src="' + esc(p.photo) + '" alt="' + esc(p.title) + '"></div><div><span class="eyebrow rv">قطعة الأسبوع</span><h2 class="ttl rv d1">' + esc(p.title) + '</h2><p class="lead rv d2">' + esc(p.description || '') + '</p>' +
      '<div class="meta2 rv d2"><div><small>الوزن</small><b class="num">' + p.weight.toFixed(2) + '</b> جم</div><div><small>العيار</small><b class="num">21K</b></div><div><small>الفرع</small><b>' + esc(p.branch) + '</b></div></div>' +
      '<div class="pr rv d3">' + moneyH(p.price) + '</div><div class="rv d3" style="display:flex;gap:12px;flex-wrap:wrap"><a class="btn g" href="#p-' + p.code + '">تفاصيل القطعة <svg class="i ar"><use href="#s-arr"/></svg></a><button class="btn" data-open-chat="أبغى أعرف أكثر عن ' + esc(p.title) + '">اسأل المستشار</button></div></div>';
    bindChatBtns($('#spot'));
  }

  /* ---------- collection page ---------- */
  var curCol = null, term = '';
  function renderCollection(key) {
    curCol = COLS.filter(function (c) { return c.key === key })[0] || null;
    var items = curCol ? colItems(curCol) : SITE.pieces;
    $('#colTitle').innerHTML = curCol ? esc(curCol.t) : 'كل <em>القطع</em>';
    $('#colCrumb').textContent = curCol ? curCol.t : 'المجموعات';
    $('#colLead').textContent = curCol ? curCol.s + ' — الأسعار على سعر الذهب اليوم.' : 'الأسعار على سعر الذهب اليوم.';
    var bg = (items[0] || {}).photo; $('#colBg').style.backgroundImage = bg ? "url('" + bg + "')" : '';
    $('#chips').innerHTML = '<a class="chip' + (curCol ? '' : ' on') + '" href="#collections">الكل</a>' + COLS.filter(function (c) { return colItems(c).length }).map(function (c) { return '<a class="chip' + (curCol === c ? ' on' : '') + '" href="#collection-' + c.key + '">' + c.t + '</a>' }).join('');
    var t = term.trim(); if (t) items = items.filter(function (p) { return (p.title + ' ' + p.kind + ' ' + (p.style || '') + ' ' + (p.occasion || '')).indexOf(t) >= 0 });
    $('#grid').innerHTML = items.length ? items.map(function (p, i) { return card(p, 'rv' + (i % 4 ? ' d' + (i % 4) : '')) }).join('') : '<div class="empty" style="grid-column:1/-1">ما لقينا قطع بهذا البحث. اسأل المستشار يساعدك.</div>';
    bindCards($('#grid')); reveal();
  }
  var st; $('#q').addEventListener('input', function (e) { term = e.target.value; renderCollection(curCol ? curCol.key : ''); clearTimeout(st); st = setTimeout(function () { if (term.trim().length > 1) T('search', null, term.trim()) }, 1200) });

  /* ---------- piece page ---------- */
  var openCode = null;
  function renderPiece(code, via) {
    var base = BY[code]; if (!base) { $('#pieceWrap').innerHTML = '<div class="empty" style="margin:160px 0">القطعة غير متاحة حالياً. <a class="link" href="#collections">شاهد القطع المتوفرة</a></div>'; return }
    openCode = code; T('piece_view', code, null, via === 'ai');
    function draw(p) {
      var photos = (p.photos && p.photos.length ? p.photos : [p.photo]).filter(Boolean), pct = SITE.deposit_pct || 10;
      var sim = SITE.pieces.filter(function (x) { return x.code !== p.code && (x.kind === p.kind || x.style === p.style) }).slice(0, 4);
      $('#pieceWrap').innerHTML = '<div class="pd"><div class="gal"><div class="main" id="gm"><img src="' + esc(photos[0] || '') + '" alt="' + esc(p.title) + '"></div>' +
        (photos.length > 1 ? '<div class="th">' + photos.map(function (u, i) { return '<button' + (i ? '' : ' class="on"') + ' data-ph="' + esc(u) + '"><img src="' + esc(u) + '" alt=""></button>' }).join('') + '</div>' : '') + '</div>' +
        '<div class="pi"><div class="crumbs"><a href="#home">الرئيسية</a><span>/</span><a href="#collections">المجموعات</a><span>/</span><span>' + esc(p.kind) + '</span></div>' +
        '<h1>' + esc(p.title) + '</h1>' + (p.status === 'reserved' ? '<span class="avail" style="color:var(--warn)"><i></i>محجوزة حالياً</span>' : '<span class="avail"><i></i>متوفرة · ' + esc(p.branch) + '</span>') +
        '<div class="specs"><div><small>الوزن</small><b class="num">' + p.weight.toFixed(2) + '</b> جم</div><div><small>العيار</small><b class="num">21K</b></div><div><small>رقم القطعة</small><b class="num">' + esc(p.code) + '</b></div></div>' +
        (p.description ? '<p class="desc">' + esc(p.description) + '</p>' : '') +
        '<div class="price">' + moneyH(p.price) + '</div><div class="pnote">شامل المصنعية · على سعر ذهب اليوم' + (CUR !== 'YER' ? ' · ' + esc(money(p.price, 'YER')) : '') + '</div>' +
        '<div class="acts">' + (p.status === 'available' ? '<button class="btn g" data-buy="full">اشترها بتحويل كامل</button><button class="btn" data-buy="deposit">احجزها بعربون ' + pct + '%</button>' : '') +
        '<button class="btn" data-fav2>' + (inList(p.code) ? 'في اختياراتي ♥' : 'أضف لاختياراتي ♡') + '</button><button class="btn" data-open-chat="أبغى أعرف أكثر عن ' + esc(p.title) + ' (' + p.code + ')"><svg class="b"><use href="#s-spark"/></svg>اسأل المستشار</button>' +
        '<a class="btn wide" href="#" data-share><svg class="b"><use href="#s-wa"/></svg>شاركها على واتساب</a></div></div></div>' +
        (sim.length ? '<section class="band" style="padding-top:20px"><div class="sh"><div><span class="eyebrow">تنسجم معها</span><h2 class="ttl">قطع <em>مشابهة</em></h2></div></div><div class="grid" id="simGrid">' + sim.map(function (x) { return card(x) }).join('') + '</div></section>' : '');
      $$('[data-ph]').forEach(function (b) { b.onclick = function () { $('#gm img').src = b.dataset.ph; $$('[data-ph]').forEach(function (x) { x.classList.toggle('on', x === b) }) } });
      var gm = $('#gm'); gm.onclick = function () { gm.classList.toggle('zoom'); if (!gm.classList.contains('zoom')) $('#gm img').style.transform = '' };
      gm.onmousemove = function (e) { if (!gm.classList.contains('zoom')) return; var r = gm.getBoundingClientRect(); $('#gm img').style.transform = 'scale(2.2)'; $('#gm img').style.transformOrigin = ((e.clientX - r.left) / r.width * 100) + '% ' + ((e.clientY - r.top) / r.height * 100) + '%' };
      $$('[data-buy]').forEach(function (b) { b.onclick = function () { checkout(p, b.dataset.buy, via) } });
      $('[data-fav2]').onclick = function () { toggleList(p.code, via); this.textContent = inList(p.code) ? 'في اختياراتي ♥' : 'أضف لاختياراتي ♡' };
      $('[data-share]').onclick = function (e) { e.preventDefault(); window.open('https://wa.me/?text=' + encodeURIComponent(p.title + ' — جمال المشرقي للذهب\n' + location.origin + location.pathname + '#p-' + p.code), '_blank', 'noopener') };
      bindChatBtns($('#pieceWrap')); var sg = $('#simGrid'); if (sg) bindCards(sg);
    }
    draw(base);
    if (ONLINE) fetch('/api/piece/' + encodeURIComponent(code)).then(function (r) { return r.ok ? r.json() : null }).then(function (d) { if (d && d.code === openCode && d.status !== 'hidden') draw(Object.assign({}, base, d)) }).catch(function () { });
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

  /* ---------- calculator & visit ---------- */
  var calcSent = false;
  function calc() { var p = SITE.prices; if (!p) return; var w = parseFloat($('#cw').value) || 0; $('#ct').innerHTML = w ? moneyH(w * p.k21.sell) : '—'; if (w && !calcSent) { calcSent = true; T('calc_use') } }
  $('#cw').addEventListener('input', calc);
  var vType = 'branch';
  $$('#vType button').forEach(function (b) { b.onclick = function () { vType = b.dataset.v; $$('#vType button').forEach(function (x) { x.classList.toggle('on', x === b) }); $('#vBranchL').classList.toggle('hidden', vType === 'video') } });
  $('#visitForm').onsubmit = function (e) {
    e.preventDefault(); var name = $('#vName').value.trim(), ph = $('#vPhone').value.trim(); if (!name || ph.length < 7) return toast('اكتب الاسم ورقم الجوال');
    var fav = LIST.map(function (c) { return BY[c] }).filter(Boolean).map(function (p) { return p.title + ' (' + p.code + ')' });
    var msg = 'السلام عليكم، أبغى أحجز ' + (vType === 'video' ? 'عرض بالفيديو' : 'زيارة خاصة في ' + $('#vBranch').value) + '\nالاسم: ' + name + '\nالجوال: ' + ph + '\nاليوم: ' + $('#vDate').value + ' — ' + $('#vTime').value + ($('#vNote').value ? '\nملاحظة: ' + $('#vNote').value : '') + (fav.length ? '\nالقطع اللي تهمني: ' + fav.join('، ') : '');
    var u = wa(msg); T('checkout_start', null, 'visit'); if (u) window.open(u, '_blank', 'noopener'); else toast('رقم الواتساب يُضاف قريباً');
  };

  /* ---------- branches ---------- */
  function renderBranches() {
    $('#brs').innerHTML = SITE.branches.map(function (b, i) { var map = b.map || 'https://maps.google.com/?q=' + encodeURIComponent('جمال المشرقي للذهب ' + b.addr + ' إب'); return '<div class="br rv' + (i ? ' d' + i : '') + '"><span class="n num">0' + (i + 1) + '</span><h3>' + esc(b.n) + '</h3><p>إب — ' + esc(b.addr) + '</p><div class="r"><a class="btn s" href="' + esc(map) + '" target="_blank" rel="noopener">الخريطة</a><a class="btn g s" href="#" data-link="whatsapp">راسلنا</a></div></div>' }).join('');
    $('#vBranch').innerHTML = SITE.branches.map(function (b) { return '<option>' + esc(b.n) + '</option>' }).join('');
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
      (items.length ? items.map(function (p) { return '<div class="li"><img src="' + esc(p.photo || '') + '" data-open="' + p.code + '" alt=""><div class="t"><b>' + esc(p.title) + '</b><span class="num">' + p.weight.toFixed(2) + ' جم</span></div><div class="p num">' + fmt(conv(p.price)) + '</div><button data-rm="' + p.code + '" aria-label="حذف" style="color:var(--faint)">' + X + '</button></div>' }).join('') : '<div class="empty" style="margin-top:20px">ما أضفت قطع بعد. اضغط ♡ على أي قطعة تعجبك.</div>') + '</div>' +
      (items.length ? '<div class="ft2"><div class="tot"><span>المجموع على سعر اليوم</span><b>' + moneyH(tot) + '</b></div><a class="btn g full" id="sendList" href="#"><svg class="b"><use href="#s-wa"/></svg>أرسل اختياراتي على واتساب</a><a class="btn full" href="#visit" data-close>احجز زيارة لمشاهدتها</a></div>' : '');
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
    else if (['collections', 'bride', 'gold', 'visit'].indexOf(h) >= 0) pg = h;
    else if (h === 'branches' || h === 'home') pg = 'home';
    var changed = pg !== ROUTE || pg === 'piece' || pg === 'collections'; ROUTE = pg;
    $$('.page').forEach(function (p) { p.classList.toggle('on', p.id === 'pg-' + pg) });
    $$('#nav a').forEach(function (a) { a.classList.toggle('on', a.dataset.r === pg || (pg === 'piece' && a.dataset.r === 'collections')) });
    if (pg === 'collections') { renderCollection(arg); T('collection_open', null, arg || 'all') }
    if (pg === 'piece') renderPiece(arg.toUpperCase(), PENDING_VIA); PENDING_VIA = null;
    if (pg === 'bride') { renderBride(); T('bride_open') }
    if (pg === 'gold') { renderTicker(); calc() }
    if (changed) { if (h === 'branches') setTimeout(function () { $('#branches').scrollIntoView() }, 60); else window.scrollTo(0, 0) }
    T('page_view', null, pg); reveal(); scrollFx();
  }
  var PENDING_VIA = null;
  window.openPiece = function (code, via) { PENDING_VIA = via; location.hash = 'p-' + code };
  addEventListener('hashchange', route);

  /* ---------- motion: header, reveals, parallax, cursor glow, magnetic buttons ---------- */
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target) } }) }, { threshold: .12 }) : null;
  function reveal() { $$('.page.on .rv:not(.in), .page.on .wipe:not(.in), footer .rv:not(.in)').forEach(function (e) { io ? io.observe(e) : e.classList.add('in') }) }
  var lastY = 0;
  function scrollFx() {
    var y = scrollY, hdr = $('#hdr');
    hdr.classList.toggle('solid', y > 40 || ROUTE !== 'home');
    hdr.classList.toggle('up', y > 400 && y > lastY + 4 && !$('#chat').classList.contains('open')); if (y < lastY - 4) hdr.classList.remove('up'); lastY = y;
    if (REDUCED || ROUTE !== 'home') return;
    var vh = innerHeight; sceneFx(vh); hscFx(vh);
    // hero: the image sinks and dims as you leave
    var hr = $('#hero').getBoundingClientRect(), hp = clamp(-hr.top / vh, 0, 1);
    $('#slides').style.transform = 'translate3d(0,' + (hp * 22).toFixed(1) + '%,0) scale(' + (1 + hp * .08).toFixed(3) + ')';
    $('.hero .inner').style.opacity = (1 - hp * 1.4).toFixed(3); $('.hero .inner').style.transform = 'translate3d(0,' + (hp * -60).toFixed(1) + 'px,0)';
    // spotlight + banner parallax
    var sp = $('#spotPh img'); if (sp) { var r = sp.parentNode.getBoundingClientRect(), t = (r.top + r.height / 2 - vh / 2) / vh; sp.style.transform = 'translate3d(0,' + (t * -8).toFixed(2) + '%,0) scale(1.04)' }
    var bb = $('#brideBg'); if (bb) { var r2 = bb.parentNode.getBoundingClientRect(), t2 = (r2.top + r2.height / 2 - vh / 2) / vh; bb.style.transform = 'translate3d(0,' + (t2 * -10).toFixed(2) + '%,0) scale(1.08)' }
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
    var h = $('#hsc'), r = h.getBoundingClientRect(); if (r.bottom < 0 || r.top > vh) return;
    var tr = $('#hTrack'), max = tr.scrollWidth - innerWidth; if (max <= 0) return;
    var p = clamp(-r.top / (r.height - vh), 0, 1);
    tr.style.transform = 'translate3d(' + (p * max).toFixed(1) + 'px,0,0)';
    var its = $$('.hit', tr), mid = innerWidth / 2, n = 0;
    its.forEach(function (el, i) { var q = el.getBoundingClientRect(), d = (q.left + q.width / 2 - mid) / innerWidth; el.querySelector('img').style.transform = 'scale(1.15) translate3d(' + (d * -12).toFixed(2) + '%,0,0)'; el.style.transform = 'rotate(' + (d * 3).toFixed(2) + 'deg) translateY(' + (Math.abs(d) * 40).toFixed(1) + 'px)'; if (Math.abs(d) < .3) n = i });
    $('#hCount').textContent = ('0' + (n + 1)).slice(-2) + ' / ' + ('0' + its.length).slice(-2);
  }
  function renderAll() { renderScene(); renderHsc(); renderTicker(); renderHomeCols(); renderNew(); renderSpot(); renderBranches(); calc(); saveList(); bindLinks(); bindChatBtns() }

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
      body = '<div class="choice"><button class="opt" data-k="full"><b>شراء بتحويل كامل المبلغ</b><span>السعر يثبت بسعر الذهب وقت التحويل، وتستلم القطعة من الفرع بعد تأكيد المحاسب.</span><span class="amt num">' + esc(money(p.price)) + '</span></button>' +
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
        '<label class="fld"><span>اسم المحوِّل كما في الإيصال</span><input class="inp" id="fPayer" maxlength="80"></label><label class="drop" id="drop"><input type="file" id="fRec" accept="image/*" hidden><span id="dropTx">اضغط لإرفاق صورة إيصال التحويل</span><img id="recPrev" class="hidden" alt=""></label>' +
        '<button class="btn g full" id="submit" style="margin-top:14px">أرسل الطلب للمراجعة</button><div class="err" id="ckErr"></div>';
    } else {
      body = '<div class="done"><div class="ok"><svg class="i" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></div><h3 class="h" style="font-size:24px;margin:0 0 6px">وصل طلبك</h3><p style="color:var(--mut);margin:0 0 10px">رقم الطلب <b class="num">' + esc(CK.number || '') + '</b> — قيد المراجعة</p><p class="note">المحاسب يراجع التحويل ويتواصل معك. الطلب يصير رسمياً بعد التأكيد، والاستلام من الفرع بفاتورة رسمية.</p><button class="btn full" data-cx>تم</button></div>';
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
      var d = { code: p.code, kind: CK.kind, token: CK.token, name: $('#fName').value.trim(), phone: $('#fPhone').value.trim(), payer: $('#fPayer').value.trim(), receipt: CK.receipt, session: window.T.session };
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
    chatEl.classList.add('open'); T('ai_open'); chatUsed = true; hideHint(); document.body.classList.remove('has-hint'); if (innerWidth < 760) document.body.style.overflow = 'hidden';
    if (!msgs.children.length) { addMsg('حياك الله في جمال المشرقي أنا مستشارك الخاص، أعرف كل قطعة متوفرة وسعرها اليوم. تجهّز لمناسبة، ولا تدور على شيء معيّن؟', 'a'); chips(['أطقم العرايس', 'عقود', 'سعر الذهب اليوم', 'وين فروعكم؟']) }
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
      return '<div class="pc" style="animation-delay:' + (i * .12) + 's" data-code="' + esc(p.code) + '"><div class="im">' + (photo ? '<img src="' + esc(photo) + '" alt="">' : '') + '</div><div class="tx"><b>' + esc(p.title) + '</b><div class="mt num">' + p.karat + 'K · ' + Number(p.weight).toFixed(2) + ' جم</div><div class="pp">' + esc(money(p.price)) + '</div><div class="avl">' + (p.status === 'reserved' ? 'محجوزة حالياً' : 'متوفرة · ' + esc(p.branch)) + '</div><div class="row"><button data-d>التفاصيل</button><button data-l>♡ أضف</button></div></div></div>';
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
  function send(t) {
    t = (t || '').trim(); if (!t || busy) return; busy = true;
    addMsg(t, 'u'); $('#chatIn').value = ''; chips([]); T('ai_message', null, null, 1);
    var ty = addMsg('', 'a'); ty.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
    var done = function (d) {
      busy = false; ty.remove(); addMsg(d.text || '…', 'a'); cards(d.pieces);
      if (d.handoff !== undefined) {
        var a = document.createElement('a'); a.className = 'handoff'; a.target = '_blank'; a.rel = 'noopener';
        a.innerHTML = '<svg class="b"><use href="#s-wa"/></svg>راسلنا على واتساب'; a.href = d.handoff || wa('السلام عليكم، تواصلت معكم من الموقع') || '#';
        a.onclick = function (e) { T('ai_handoff_click', null, null, 1); if (a.getAttribute('href') === '#') { e.preventDefault(); toast('رقم الواتساب يُضاف قريباً') } };
        msgs.appendChild(a); msgs.scrollTop = 1e6;
      }
      chips(d.suggest);
    };
    if (!ONLINE || !SITE.ai) { setTimeout(function () { done(localReply(t)) }, 700); return }
    fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session: CHAT_ID, message: t }) })
      .then(function (r) { return r.json() }).then(done).catch(function () { done(localReply(t)) });
  }
  $('#chatForm').onsubmit = function (e) { e.preventDefault(); send($('#chatIn').value) };
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
    { t: 'محتار وش تختار؟ أنا هنا أساعدك', q: '' },
    { t: 'قل لي المناسبة، وأرشّح لك الأنسب من قطع اليوم', q: '' },
    { t: 'تبي تعرف سعر قطعة على ذهب اليوم؟ اسألني', q: '' },
    { t: 'عندي أفكار تنسيقات تليق بك 💫', q: 'أبغى أفكار تنسيقات' },
    { t: 'تجهّز لعرس؟ خلني أرتب لك باقة متكاملة', q: 'أبغى أجهز باقة عروس' },
    { t: 'تدور هدية تفرّح؟ أقترح لك على ميزانيتك', q: 'أبغى هدية' },
    { t: 'تفضّل الناعم ولا الفخم؟ قل لي وأطلع لك الأقرب لذوقك', q: '' }], hintN = 0, chatUsed = false, hintHide;
  function hint() {
    if (chatUsed || chatEl.classList.contains('open') || $('#modal').classList.contains('open') || hintN >= HINTS.length) return;
    if (hintN === 0) HINTS.sort(function () { return Math.random() - .5 }); var h = HINTS[hintN++]; $('#aibTx').textContent = h.t; $('#aib').dataset.q = h.q;
    $('#aib').classList.add('on'); document.body.classList.add('has-hint');
    clearTimeout(hintHide); hintHide = setTimeout(hideHint, 6500);
  }
  function hideHint() { $('#aib').classList.remove('on') }
  $('#aib').onclick = function () { var q = this.dataset.q; hideHint(); openChat(q || undefined) };
  [7000, 28000, 55000, 90000, 140000].forEach(function (ms) { setTimeout(hint, ms) });


  /* ---------- boot ---------- */
  function boot() {
    BY = {}; SITE.pieces.forEach(function (p) { BY[p.code] = p });
    $$('#cur button').forEach(function (b) { b.classList.toggle('on', b.dataset.c === CUR) });
    renderHero(); renderAll();
    var bp = SITE.pieces.filter(function (p) { return p.kind === 'طقم' && p.photo && p.style === 'فخم' }).pop() || SITE.pieces[0];
    if (bp) { $('#brideBg').style.backgroundImage = "url('" + bp.photo + "')"; $('#brideHeadBg').style.backgroundImage = "url('" + bp.photo + "')"; $('#visitBg').style.backgroundImage = "url('" + (SITE.pieces[1] || bp).photo + "')" }
    $('#yr').textContent = new Date().getFullYear(); route();
  }
  (ONLINE ? fetch('/api/site').then(function (r) { if (!r.ok) throw 0; return r.json() }) : Promise.reject())
    .then(function (d) { if (d && d.v === 2) SITE = d; else throw 0 }).catch(function () { ONLINE = false; window.GM_OFFLINE = true }).then(boot);
  var t0 = Date.now(), qs = new URLSearchParams(location.search);
  addEventListener('load', function () { setTimeout(hideSplash, qs.get('nosplash') ? 0 : Math.max(0, 1200 - (Date.now() - t0))) });
})();

/* لوحة الإدارة — تحليلات الموقع، المساعد، الطلبات، الإعدادات */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s) }, $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)) };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] }) };
  var fmt = function (n, d) { return Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: d || 0, minimumFractionDigits: d || 0 }) };
  var usd = function (n) { n = Number(n || 0); return '$' + (n < 0.01 && n > 0 ? n.toFixed(5) : n < 1 ? n.toFixed(4) : n.toFixed(2)) };
  
  var tt; function toast(m) { var t = $('#toast'); t.textContent = m; t.classList.add('on'); clearTimeout(tt); tt = setTimeout(function () { t.classList.remove('on') }, 2600) }
  function api(p, body) {
    return fetch(p, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' } : { credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (d) { if (r.status === 401) { loginView(); throw d } if (!r.ok) throw d; return d }) });
  }
  var ME = null, TAB = 'stock', RANGE = 7;
  function iso(d) { return d.toISOString().slice(0, 10) }
  function range() { var b = new Date(), a = new Date(); a.setDate(b.getDate() - (RANGE - 1)); return 'a=' + iso(a) + '&b=' + iso(b) }

  function loginView() {
    $('#app').innerHTML = '<div class="login"><form class="card2" id="lf"><img src="/img/logo_night.png" class="lg-night" alt=""><h2 class="h" style="text-align:center;margin:0 0 18px">لوحة الإدارة</h2>' +
      '<label class="fld"><span>اسم المستخدم</span><input class="inp" id="lu" autocomplete="username"></label><label class="fld"><span>كلمة السر</span><input class="inp" id="lp" type="password" autocomplete="current-password"></label>' +
      '<button class="btn g full">دخول</button><div class="err" id="le"></div></form></div>';
    $('#lf').onsubmit = function (e) { e.preventDefault(); api('/api/admin/login', { username: $('#lu').value, password: $('#lp').value }).then(boot).catch(function (x) { $('#le').textContent = (x && x.error) || 'تعذر الدخول' }) };
  }
  var TABS = [['stock', 'المخزون والبيع'], ['overview', 'نظرة عامة'], ['journey', 'رحلة العميل'], ['products', 'تفاعل القطع'], ['ai', 'أداء المساعد والتكلفة'], ['requests', 'الطلبات والتحويلات'], ['chats', 'محادثات المساعد'], ['demand', 'طلبات غير متوفرة'], ['agent', 'الوكيل'], ['settings', 'الإعدادات']];
  function shell() {
    $('#app').innerHTML = '<div class="lay"><aside><img src="/img/logo_night.png" class="lg-night" alt=""><img src="/img/logo_day.png" class="lg-day" alt="" style="display:none">' +
      TABS.filter(function (t) { return ME.role !== 'accountant' || t[0] === 'requests' }).map(function (t) { return '<button data-t="' + t[0] + '"' + (t[0] === TAB ? ' class="on"' : '') + '>' + t[1] + '</button>' }).join('') +
      '<span class="sp"></span><div class="who">' + esc(ME.name) + (ME.mode === 'demo' ? ' · وضع التجربة' : '') + '</div><button id="out">تسجيل خروج</button></aside><div class="mainp" id="mp"></div></div>';
    $$('aside [data-t]').forEach(function (b) { b.onclick = function () { TAB = b.dataset.t; $$('aside [data-t]').forEach(function (x) { x.classList.toggle('on', x === b) }); load() } });
    $('#out').onclick = function () { api('/api/admin/logout', {}).then(loginView) };
  }
  function head(title, rng) {
    return '<div class="top2"><h1>' + title + '</h1>' + (rng ? '<div class="rng">' + [[1, 'اليوم'], [7, '7 أيام'], [30, '30 يوم'], [90, '90 يوم']].map(function (r) { return '<button data-r="' + r[0] + '"' + (r[0] === RANGE ? ' class="on"' : '') + '>' + r[1] + '</button>' }).join('') + '</div>' : '') + '</div>';
  }
  function bindRange() { $$('[data-r]').forEach(function (b) { b.onclick = function () { RANGE = +b.dataset.r; load() } }) }
  function delta(c, p) { if (!p) return '<span class="d">—</span>'; var d = Math.round((c - p) / p * 100); return '<span class="d ' + (d >= 0 ? 'up' : 'dn') + '">' + (d >= 0 ? '▲ ' : '▼ ') + Math.abs(d) + '% عن الفترة السابقة</span>' }
  function kpi(label, v, prev, raw) { return '<div class="kp"><small>' + label + '</small><b>' + (raw || fmt(v)) + '</b>' + (prev === undefined ? '' : delta(v, prev)) + '</div>' }

  /* --- charts (SVG, single gold series, quiet axes) --- */
  function area(series, key, label) {
    var W = 640, H = 220, P = 28, n = series.length; if (!n) return '<div class="sub">لا توجد بيانات بعد</div>';
    var max = Math.max.apply(null, series.map(function (s) { return s[key] || 0 }).concat([1]));
    var x = function (i) { return n === 1 ? W / 2 : P + i * (W - 2 * P) / (n - 1) }, y = function (v) { return H - P - (v / max) * (H - 2 * P) };
    var pts = series.map(function (s, i) { return x(i).toFixed(1) + ',' + y(s[key] || 0).toFixed(1) }).join(' ');
    var ticks = series.map(function (s, i) { return (n <= 10 || i % Math.ceil(n / 8) === 0) ? '<text x="' + x(i) + '" y="' + (H - 8) + '" text-anchor="middle">' + s.day.slice(5) + '</text>' : '' }).join('');
    return '<svg class="ch" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" aria-label="' + label + '"><defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d6b26a" stop-opacity=".35"/><stop offset="1" stop-color="#d6b26a" stop-opacity="0"/></linearGradient></defs>' +
      '<line class="ax" x1="' + P + '" y1="' + (H - P) + '" x2="' + (W - P) + '" y2="' + (H - P) + '"/><text x="' + P + '" y="' + (P - 8) + '">' + fmt(max) + '</text>' +
      '<polygon fill="url(#ga)" points="' + x(0) + ',' + (H - P) + ' ' + pts + ' ' + x(n - 1) + ',' + (H - P) + '"/><polyline fill="none" stroke="#d6b26a" stroke-width="2.2" points="' + pts + '"/>' +
      series.map(function (s, i) { return '<circle cx="' + x(i) + '" cy="' + y(s[key] || 0) + '" r="3.2" fill="#d6b26a"><title>' + s.day + ': ' + fmt(s[key]) + '</title></circle>' }).join('') + ticks + '</svg>';
  }
  function bars(rows, kx, ky) {
    var W = 640, H = 220, P = 24, map = {}; rows.forEach(function (r) { map[r[kx]] = r[ky] });
    var arr = []; for (var i = 0; i < 24; i++) arr.push(map[i] || 0);
    var max = Math.max.apply(null, arr.concat([1])), bw = (W - 2 * P) / 24;
    return '<svg class="ch" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + arr.map(function (v, i) { var bh = (v / max) * (H - 2 * P); return '<rect x="' + (P + i * bw + 2) + '" y="' + (H - P - bh) + '" width="' + (bw - 4) + '" height="' + bh + '" rx="2" fill="#d6b26a" opacity="' + (v ? .9 : .15) + '"><title>' + i + ':00 — ' + v + '</title></rect>' + (i % 3 === 0 ? '<text x="' + (P + i * bw + bw / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + i + '</text>' : '') }).join('') + '</svg>';
  }
  var STEP = { visit: 'زيارة الموقع', piece_view: 'مشاهدة قطعة', ai_open: 'فتح المساعد', ai_card_shown: 'المساعد عرض قطع', ai_card_click: 'ضغط على بطاقة', shortlist_add: 'أضاف لاختياراتي', checkout_start: 'بدأ حجز/شراء', request_submit: 'أرسل طلب بتحويل' };
  function funnel(steps) {
    var top = (steps[0] || {}).sessions || 0;
    return '<div class="fn">' + steps.map(function (s, i) {
      var pct = top ? s.sessions / top * 100 : 0, prev = i ? steps[i - 1].sessions : 0, drop = i && prev ? Math.round(100 - s.sessions / prev * 100) : null;
      return '<div class="fr"><span>' + (STEP[s.step] || s.step) + '</span><div class="bar"><i style="width:' + Math.max(pct, s.sessions ? 2 : 0).toFixed(1) + '%"></i></div><span class="v">' + fmt(s.sessions) + ' <small>' + (drop !== null ? (drop > 0 ? '−' + drop + '%' : '') : '') + '</small></span></div>';
    }).join('') + '</div>';
  }

  function load() {
    var mp = $('#mp'); mp.innerHTML = '<div class="sub">جاري التحميل…</div>';
    var go = ({ stock: stock, overview: overview, journey: journey, products: products, ai: ai, requests: requests, chats: chats, demand: demand, agent: agentTab, settings: settings })[TAB];
    go(mp);
  }
  // one stock for the shop and the website: sell a piece from any branch and it leaves the site at once
  var STQ = '';
  var STN = { available: ['متاحة', 'ok'], reserved: ['محجوزة', 'w'], sold: ['مباعة', 'x'], inactive: ['موقوفة', 'x'], transfer: ['تحويل', 'w'] };
  function stock(mp) {
    if (ME.role === 'accountant') { TAB = 'requests'; return load() }
    api('/api/admin/stock?q=' + encodeURIComponent(STQ)).then(function (rows) {
      mp.innerHTML = head('المخزون والبيع') + '<div class="sub" style="margin:-6px 0 16px">نفس مخزون المحل. القطعة اللي تُباع هنا تختفي من الموقع خلال ثوانٍ، ولا يقدر أحد يحجزها.</div>' +
        '<div class="box"><input class="inp" id="stq" placeholder="ابحث برقم القطعة أو نوعها" value="' + esc(STQ) + '" style="width:100%;margin-bottom:14px">' +
        '<table class="tbl"><thead><tr><th>القطعة</th><th>الوزن</th><th>الفرع</th><th>الحالة</th><th>السعر الآن</th><th></th></tr></thead><tbody>' +
        (rows.length ? rows.map(function (r) { var s = STN[r.status] || [r.status, '']; return '<tr><td>' + esc(r.title) + ' <span class="sub" style="margin:0">' + esc(r.code) + '</span></td><td class="n">' + Number(r.weight).toFixed(2) + '</td><td>' + esc(r.branch) + '</td><td><span class="tag ' + s[1] + '">' + s[0] + '</span>' + (r.online ? '' : ' <span class="sub" style="margin:0">مخفية من الموقع</span>') + '</td><td class="n">' + (r.price ? fmt(r.price) : '—') + '</td><td>' +
          (r.status === 'available' || r.status === 'reserved' ? '<button class="btn s g" data-sell="' + esc(r.code) + '">تسجيل بيع</button> ' : '') +
          (r.status === 'available' ? '<button class="btn s" data-st="inactive" data-c="' + esc(r.code) + '">إيقاف</button>' : r.status === 'inactive' ? '<button class="btn s" data-st="available" data-c="' + esc(r.code) + '">تفعيل</button>' : '') + '</td></tr>' }).join('') : '<tr><td colspan="6" class="sub">لا توجد قطع</td></tr>') + '</tbody></table></div>';
      var t; $('#stq').oninput = function (e) { clearTimeout(t); t = setTimeout(function () { STQ = e.target.value; load() }, 400) };
      mp.querySelectorAll('[data-sell]').forEach(function (b) { b.onclick = function () {
        var code = b.dataset.sell, name = prompt('تسجيل بيع القطعة ' + code + '\nاسم العميل (اختياري):', ''); if (name === null) return;
        b.disabled = true; api('/api/admin/sell', { code: code, name: name }).then(function (r) { toast('تم البيع — فاتورة ' + (r.invoice || '')); load() }).catch(function (e) { b.disabled = false; toast(e.error || 'خطأ') });
      } });
      mp.querySelectorAll('[data-st]').forEach(function (b) { b.onclick = function () { api('/api/admin/piece_status', { code: b.dataset.c, status: b.dataset.st }).then(function () { toast('تم'); load() }).catch(function (e) { toast(e.error || 'خطأ') }) } });
    }).catch(function (e) { mp.innerHTML = '<div class="sub">' + esc(e.error || 'خطأ') + '</div>' });
  }
  function overview(mp) {
    api('/api/admin/analytics?s=overview&' + range()).then(function (d) {
      var k = d.kpi, p = d.prev;
      mp.innerHTML = head('نظرة عامة', 1) + '<div class="kpis">' + kpi('الزوار', k.visitors, p.visitors) + kpi('الجلسات', k.sessions, p.sessions) + kpi('مشاهدات القطع', k.piece_views, p.piece_views) + kpi('محادثات المساعد', k.ai_chat, p.ai_chat) +
        kpi('أضافوا لاختياراتي', k.shortlist, p.shortlist) + kpi('طلبات بتحويل', k.requests, p.requests) + kpi('التحويل: زيارة ← طلب', 0, undefined, k.conv_visit_to_request + '%') + kpi('متوسط مدة الجلسة', 0, undefined, Math.round(k.avg_duration_s / 60) + 'د ' + (k.avg_duration_s % 60) + 'ث') + '</div>' +
        '<div class="g2"><div class="box"><h3>الزيارات عبر الوقت</h3><div class="sub">جلسات يومية</div>' + area(d.series, 'sessions', 'الجلسات') + '</div><div class="box"><h3>النشاط حسب الساعة</h3><div class="sub">أوقات دخول الزوار</div>' + bars(d.hours, 'hour', 'sessions') + '</div></div>' +
        '<div class="g3"><div class="box"><h3>أين يغادر الزوار</h3><div class="sub">آخر صفحة قبل الخروج</div><div class="list2">' + (d.exits.map(function (e) { return '<div><span>' + esc(e.page || '/') + '</span><b>' + fmt(e.n) + '</b></div>' }).join('') || '<div class="sub">—</div>') + '</div></div>' +
        '<div class="box"><h3>ماذا يبحث الناس</h3><div class="sub">كلمات البحث في الموقع</div><div class="list2">' + (d.searches.map(function (e) { return '<div><span>' + esc(e.term) + '</span><b>' + fmt(e.n) + '</b></div>' }).join('') || '<div class="sub">—</div>') + '</div></div>' +
        '<div class="box"><h3>زوار جدد وعائدون</h3><div class="sub">حسب ما يقيسه المتصفح</div><div class="list2"><div><span>جدد</span><b>' + fmt(k.new_visitors) + '</b></div><div><span>عائدون</span><b>' + fmt(Math.max(0, k.visitors - k.new_visitors)) + '</b></div><div><span>ضغطات واتساب</span><b>' + fmt(k.whatsapp) + '</b></div></div></div></div>';
      bindRange();
    }).catch(err(mp));
  }
  function journey(mp) {
    api('/api/admin/analytics?s=funnel&' + range()).then(function (f) {
      return api('/api/admin/analytics?s=sessions&' + range()).then(function (ss) {
        mp.innerHTML = head('رحلة العميل', 1) + '<div class="g2"><div class="box"><h3>مسار الموقع</h3><div class="sub">عدد الجلسات في كل خطوة — والنسبة اللي نخسرها بين الخطوات</div>' + funnel(f.site) + '</div><div class="box"><h3>مسار المساعد الذكي</h3><div class="sub">من فتح المساعد إلى الطلب</div>' + funnel(f.ai) + '</div></div>' +
          '<div class="box"><h3>آخر الجلسات</h3><div class="sub">اضغط على جلسة لرؤية رحلتها خطوة بخطوة (بدون بيانات شخصية)</div><table class="scn"><tr><th>آخر نشاط</th><th>الجهاز</th><th>أحداث</th><th>رسائل للمساعد</th><th>طلبات</th></tr>' +
          ss.map(function (s) { return '<tr data-s="' + esc(s.session) + '" style="cursor:pointer"><td class="n">' + esc(s.last_ts.slice(5, 16)) + '</td><td>' + (s.device === 'mobile' ? 'جوال' : 'كمبيوتر') + (s.is_new ? ' · جديد' : '') + '</td><td class="n">' + s.events + '</td><td class="n">' + s.ai_msgs + '</td><td class="n">' + s.requests + '</td></tr>' }).join('') + '</table><div id="path"></div></div>';
        bindRange();
        $$('[data-s]').forEach(function (r) { r.onclick = function () { api('/api/admin/path?id=' + r.dataset.s).then(function (p) { $('#path').innerHTML = '<div class="list2" style="margin-top:14px">' + p.map(function (e) { return '<div><span>' + esc(e.ts.slice(11)) + ' — ' + esc(EV[e.type] || e.type) + (e.code ? ' · ' + esc(e.code) : '') + (e.via_ai ? ' (من المساعد)' : '') + '</span><b></b></div>' }).join('') + '</div>' }) } });
      });
    }).catch(err(mp));
  }
  var EV = { page_view: 'دخل الموقع', piece_view: 'شاهد قطعة', search: 'بحث', filter: 'فلتر', collection_open: 'فتح مجموعة', calc_use: 'استخدم الحاسبة', bride_open: 'فتح باقة العروس', shortlist_add: 'أضاف لاختياراتي', shortlist_remove: 'حذف من اختياراتي', checkout_start: 'بدأ حجز/شراء', terms_accept: 'وافق على الشروط', request_submit: 'أرسل طلب', checkout_abandon: 'انسحب قبل الإرسال', whatsapp_click: 'ضغط واتساب', social_click: 'ضغط سوشال', branch_map: 'فتح خريطة فرع', ai_open: 'فتح المساعد', ai_message: 'راسل المساعد', ai_card_shown: 'المساعد عرض قطعة', ai_card_click: 'ضغط بطاقة من المساعد', ai_detail_open: 'فتح تفاصيل من المساعد', ai_suggest_click: 'ضغط اقتراح', ai_handoff_click: 'تواصل مع صاحب المحل', ai_add_shortlist: 'أضاف من المساعد', ai_close: 'أغلق المساعد' };
  function products(mp) {
    api('/api/admin/analytics?s=products&' + range()).then(function (rows) {
      rows.sort(function (a, b) { return b.views - a.views });
      mp.innerHTML = head('تفاعل القطع', 1) + '<div class="box"><h3>القطع حسب الاهتمام</h3><div class="sub">المشاهدات، اقتراحات المساعد، الإضافة لاختياراتي، والطلبات</div><table><tr><th></th><th>القطعة</th><th>مشاهدات</th><th>عرضها المساعد</th><th>ضغطات من المساعد</th><th>أضيفت</th><th>بدأ طلب</th><th>طلبات</th><th>مشاهدة ← إضافة</th><th></th></tr>' +
        rows.map(function (r) { return '<tr><td>' + (r.photo ? '<img src="' + esc(r.photo) + '" alt="">' : '') + '</td><td>' + esc(r.title) + '<div class="sub" style="margin:0">' + esc(r.code) + '</div></td><td class="n">' + fmt(r.views) + '</td><td class="n">' + fmt(r.ai_shown) + '</td><td class="n">' + fmt(r.ai_clicks) + '</td><td class="n">' + fmt(r.shortlisted) + '</td><td class="n">' + fmt(r.checkouts) + '</td><td class="n">' + fmt(r.requests) + '</td><td class="n">' + r.view_to_list + '%</td><td>' + (r.interest_no_request ? '<span class="tag w">اهتمام بدون طلب</span>' : '') + '</td></tr>' }).join('') + '</table>' + (rows.length ? '' : '<div class="sub" style="margin-top:12px">لا توجد بيانات بعد</div>') + '</div>';
      bindRange();
    }).catch(err(mp));
  }
  function ai(mp) {
    api('/api/admin/analytics?s=ai&' + range()).then(function (d) {
      var u = d.usage, e = d.events || {}, pj = d.projection;
      mp.innerHTML = head('أداء المساعد والتكلفة', 1) +
        '<div class="kpis">' + kpi('فتحوا المساعد', d.opened) + kpi('تحدثوا معه', d.chatted) + kpi('متوسط الرسائل للجلسة', 0, undefined, fmt(u.avg_msgs, 1)) + kpi('نسبة الزوار اللي استخدموه', 0, undefined, u.usage_rate + '%') +
        kpi('بطاقات قطع عرضها', e.shown || 0) + kpi('ضغطات على البطاقات', e.clicks || 0) + kpi('تحويل لصاحب المحل', d.handoffs) + kpi('طلبات بعد المحادثة', d.requests_after_ai) + '</div>' +
        '<div class="g2"><div class="box"><h3>التكلفة الفعلية <span class="mes">مقاسة</span></h3><div class="sub">من سجلات كل طلب — النموذج الأساسي: ' + esc(d.model) + (d.model_strong ? ' · للحظات الحاسمة: ' + esc(d.model_strong) : '') + '</div><div class="list2">' +
        '<div><span>إجمالي الفترة</span><b>' + usd(u.cost) + '</b></div><div><span>اليوم / هذا الشهر</span><b>' + usd(d.spent_today) + ' / ' + usd(d.spent_month) + '</b></div><div><span>السقف اليومي / الشهري</span><b>' + usd(d.caps.day) + ' / ' + usd(d.caps.month) + '</b></div>' +
        '<div><span>عدد الطلبات (منها مجانية)</span><b>' + fmt(u.requests) + ' (' + fmt(u.canned) + ')</b></div><div><span>توكنز داخل / مكرر / خارج</span><b>' + fmt(u.t_in) + ' / ' + fmt(u.t_cached) + ' / ' + fmt(u.t_out) + '</b></div>' +
        '<div><span>تكلفة الرسالة</span><b>' + usd(u.cost_per_message) + '</b></div><div><span>تكلفة الجلسة</span><b>' + usd(u.cost_per_session) + '</b></div><div><span>تكلفة كل 100 / 1,000 زائر</span><b>' + usd(u.cost_per_100_visitors) + ' / ' + usd(u.cost_per_1000_visitors) + '</b></div></div>' +
        area(d.per_day.map(function (r) { return { day: r.day, cost: r.cost * 1000 } }), 'cost', 'التكلفة') + '<div class="sub">الرسم: التكلفة اليومية × 1000 دولار</div></div>' +
        '<div class="box"><h3>توقع التكلفة الشهرية</h3>' + (pj.measured ? '<div class="sub">مقاس <span class="mes">من بياناتكم</span> — بنفس نسبة الاستخدام ومتوسط الرسائل</div><div class="list2">' + pj.measured.monthly.map(function (m) { return '<div><span>' + fmt(m.visitors) + ' زائر يومياً</span><b>' + usd(m.usd) + '</b></div>' }).join('') + '</div>' : '<div class="sub">يظهر التوقع المقاس بعد أول محادثات حقيقية.</div>') +
        '<div class="sub" style="margin-top:16px">سيناريو <span class="est">تقديري</span> — ' + esc(pj.scenario.assumptions) + '</div><table><tr><th>زوار/يوم</th><th>استخدام</th><th>رسائل</th><th>يومياً</th><th>شهرياً</th></tr>' +
        pj.scenario.rows.map(function (r) { return '<tr><td class="n">' + fmt(r.visitors) + '</td><td class="n">' + r.usage_rate + '%</td><td class="n">' + r.msgs + '</td><td class="n">' + usd(r.usd_day) + '</td><td class="n">' + usd(r.usd_month) + '</td></tr>' }).join('') + '</table></div></div>' +
        '<div class="g3"><div class="box"><h3>أكثر الاحتياجات</h3><div class="sub">تجميعي، بدون نصوص المحادثات</div><div class="list2">' + (d.needs.map(function (n) { return '<div><span>' + esc(n.need) + '</span><b>' + fmt(n.n) + '</b></div>' }).join('') || '—') + '</div></div>' +
        '<div class="box"><h3>مراحل المحادثات</h3><div class="sub">زائر عادي ← مهتم ← تنسيق ← جاد</div><div class="list2">' + (d.stages.map(function (n) { return '<div><span>' + esc(({ browse: 'زائر عادي', interest: 'مهتم', taste: 'تنسيق/ذوق', objection: 'تردد/اعتراض', ready: 'نية شراء جدية' })[n.stage] || n.stage) + '</span><b>' + fmt(n.n) + '</b></div>' }).join('') || '—') + '</div></div>' +
        '<div class="box"><h3>القطع اللي نجح فيها المساعد</h3><div class="sub">عرض ← ضغط ← إضافة</div><div class="list2">' + (d.top_pieces.map(function (n) { return '<div><span>' + esc(n.code) + '</span><b>' + fmt(n.shown) + ' ← ' + fmt(n.clicks) + ' ← ' + fmt(n.lists) + '</b></div>' }).join('') || '—') + '</div><div class="sub" style="margin-top:10px">محادثات انتهت بدون أي تفاعل: ' + fmt(d.silent_sessions) + '</div></div></div>';
      bindRange();
    }).catch(err(mp));
  }
  function requests(mp) {
    api('/api/admin/requests').then(function (rows) {
      var st = { pending: ['قيد المراجعة', 'w'], active: ['مؤكد', 'ok'], cancelled: ['ملغي', 'x'], expired: ['منتهي', 'x'], sold: ['مباع', 'ok'] };
      mp.innerHTML = head('الطلبات والتحويلات') + '<div class="box"><div class="sub">لا يُؤكد أي طلب إلا بعد التأكد من وصول المبلغ في الحساب — صورة الإيصال وحدها لا تكفي.</div><table><tr><th>الرقم</th><th>النوع</th><th>القطعة</th><th>العميل</th><th>المحوِّل</th><th>المبلغ</th><th>الحالة</th><th>الإيصال</th><th></th></tr>' +
        rows.map(function (r) { var s = st[r.status] || [r.status, '']; return '<tr><td class="n">' + esc(r.number) + '</td><td>' + (r.kind === 'full' ? 'شراء كامل' : 'عربون') + '</td><td>' + esc(r.type) + ' <span class="sub">' + esc(r.code) + '</span></td><td>' + esc(r.customer_name) + '<div class="sub" style="margin:0" dir="ltr">' + esc(r.customer_phone) + '</div></td><td>' + esc(r.payer_name || '') + '</td><td class="n">' + fmt(r.amount || r.deposit) + '</td><td><span class="tag ' + s[1] + '">' + s[0] + '</span></td><td>' + (r.receipt ? '<a class="link" target="_blank" href="/api/admin/receipt/' + esc(r.receipt) + '">عرض</a>' : '') + '</td><td>' + (r.status === 'pending' && ME.role !== 'manager' ? '<button class="btn g s" data-c="' + esc(r.number) + '">تأكيد الوصول</button> ' : '') + (r.status === 'pending' || r.status === 'active' ? '<button class="btn s" data-x="' + esc(r.number) + '">إلغاء</button>' : '') + '</td></tr>' }).join('') + '</table>' + (rows.length ? '' : '<div class="sub" style="margin-top:12px">لا توجد طلبات</div>') + '</div>';
      $$('[data-c]').forEach(function (b) { b.onclick = function () { if (!confirm('تأكدت من وصول المبلغ في الحساب؟')) return; api('/api/admin/confirm', { number: b.dataset.c }).then(function () { toast('تم التأكيد'); load() }).catch(function (e) { toast(e.error || 'خطأ') }) } });
      $$('[data-x]').forEach(function (b) { b.onclick = function () { var n = prompt('سبب الإلغاء'); if (n === null) return; api('/api/admin/close', { number: b.dataset.x, status: 'cancelled', note: n }).then(function () { toast('تم الإلغاء'); load() }).catch(function (e) { toast(e.error || 'خطأ') }) } });
    }).catch(err(mp));
  }
  function agentTab(mp) {
    mp.innerHTML = head('الوكيل الداخلي') + '<div class="sub" style="margin-bottom:12px">اسأله عن المبيعات والمخزون والحجوزات والموقع وتكلفة الذكاء. يقرأ من قاعدة البيانات مباشرة، وما يقدر يعدّل شيئاً.</div>' +
      '<div class="box"><div id="agLog" style="max-height:60vh;overflow:auto;display:flex;flex-direction:column;gap:10px;margin-bottom:12px"></div>' +
      '<div style="display:flex;gap:8px"><input class="inp" id="agQ" placeholder="مثلاً: كم مبيعات اليوم؟ وش أكثر نوع انطلب هذا الأسبوع؟" style="flex:1"><button class="btn g" id="agS">اسأل</button></div>' +
      '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px">' + ['ملخص مبيعات اليوم', 'المخزون حسب النوع', 'الحجوزات المعلقة', 'طلبات الزبائن غير المتوفرة', 'زوار الموقع وتكلفة الذكاء هذا الأسبوع'].map(function (t) { return '<button class="btn s" data-aq="' + t + '">' + t + '</button>' }).join('') + '</div></div>';
    function add(who, t) { var d = document.createElement('div'); d.style.cssText = 'white-space:pre-wrap;line-height:1.8;padding:10px 14px;border-radius:12px;max-width:85%;' + (who === 'u' ? 'align-self:flex-start;background:rgba(217,184,114,.14)' : 'align-self:flex-end;border:1px solid rgba(217,184,114,.25)'); d.textContent = t; $('#agLog').appendChild(d); $('#agLog').scrollTop = 1e9; return d }
    function ask(q) { if (!q) return; add('u', q); var w = add('a', '...'); api('/api/admin/agent', { message: q }).then(function (r) { w.textContent = r.text }).catch(function (e) { w.textContent = 'خطأ: ' + e }) }
    $('#agS').onclick = function () { var q = $('#agQ').value.trim(); $('#agQ').value = ''; ask(q) };
    $('#agQ').onkeydown = function (e) { if (e.key === 'Enter') $('#agS').click() };
    $$('[data-aq]').forEach(function (b) { b.onclick = function () { ask(b.dataset.aq) } });
  }
  function demand(mp) {
    api('/api/admin/demand').then(function (d) {
      var agg = (d.by_category || []).map(function (r) { return '<div><span>' + esc(r.category || '—') + '</span><b>' + r.n + (r.avg_budget ? ' · متوسط الميزانية ' + fmt(r.avg_budget) : '') + '</b></div>' }).join('') || '<div class="sub">لا توجد طلبات مفتوحة</div>';
      var rows = (d.rows || []).map(function (r) { var ex = []; try { ex = JSON.parse(r.excluded || '[]') } catch (e) { }
        return '<tr><td class="n">' + esc(r.ts) + '</td><td>' + esc(r.category) + '</td><td>' + esc(r.description || '') + (ex.length ? '<div class="sub">بدون: ' + esc(ex.join('، ')) + '</div>' : '') + '</td><td class="n">' + (r.budget ? fmt(r.budget) : '—') + '</td><td>' + esc(r.contact || '—') + '</td><td>' + (r.status === 'open' ? '<button class="btn s" data-dr="' + r.id + '">تم</button>' : 'منتهي') + '</td></tr>' }).join('');
      mp.innerHTML = head('طلبات غير متوفرة') + '<div class="sub" style="margin-bottom:14px">طلبات زبائن ما لقوا المطلوب، تسجلت بموافقتهم من المستشار. الأرقام من السجلات الفعلية فقط.</div><div class="g2"><div class="box"><h3>حسب النوع (المفتوحة)</h3><div class="list2">' + agg + '</div></div></div>' +
        '<div class="box"><table class="tbl"><tr><th>الوقت</th><th>النوع</th><th>الطلب</th><th>الميزانية</th><th>التواصل</th><th></th></tr>' + (rows || '<tr><td colspan="6" class="sub">لا يوجد</td></tr>') + '</table></div>';
      $$('[data-dr]').forEach(function (b) { b.onclick = function () { api('/api/admin/demand_resolve', { id: +b.dataset.dr }).then(function () { demand(mp) }) } });
    });
  }
  function chats(mp) {
    api('/api/admin/chats').then(function (d) {
      var by = {}; d.chats.slice().reverse().forEach(function (c) { (by[c.session] = by[c.session] || []).push(c) });
      mp.innerHTML = head('محادثات المساعد') + '<div class="g2"><div class="box"><h3>آخر المحادثات</h3><div class="sub">للمراجعة وتحسين المساعد</div><div class="chatlog">' + Object.keys(by).slice(-30).reverse().map(function (s) { var cost = by[s].reduce(function (a, c) { return a + (c.cost || 0) }, 0); return '<div style="border-bottom:1px solid var(--line);padding:12px 0"><div class="sub">' + esc(by[s][0].ts) + ' · تكلفة ' + usd(cost) + '</div>' + by[s].map(function (c) { return '<div class="mg ' + (c.role === 'user' ? 'u' : 'a') + '">' + esc(c.content) + '</div>' }).join('') + '</div>' }).join('') + '</div></div>' +
        '<div class="box"><h3>طلبات التحويل لصاحب المحل</h3><div class="list2">' + d.handoffs.map(function (x) { return '<div><span>' + esc(x.ts.slice(5, 16)) + ' — ' + esc(x.reason) + '<br><span class="sub">' + esc(x.summary) + '</span></span>' + (x.handled ? '<span class="tag ok">تم</span>' : '<button class="btn s" data-h="' + x.id + '">تم التواصل</button>') + '</div>' }).join('') + '</div></div></div>';
      $$('[data-h]').forEach(function (b) { b.onclick = function () { api('/api/admin/handoff_done', { id: +b.dataset.h }).then(load) } });
    }).catch(err(mp));
  }
  function ta(id, label, v) { return '<label class="fld"><span>' + label + '</span><textarea class="inp" id="t_' + id + '" rows="3" style="width:100%;resize:vertical">' + esc(v || '') + '</textarea></label>' }
  function settings(mp) {
    api('/api/admin/settings').then(function (d) {
      var p = d.prices || {}, L = d.links || {};
      mp.innerHTML = head('الإعدادات') + '<div class="g2"><div class="box"><h3>سعر الذهب اليوم</h3><div class="sub">يظهر في الموقع فوراً</div>' +
        f('k21_sell', 'جرام 21 — بيع', p.k21_sell) + f('k21_buy', 'جرام 21 — شراء', p.k21_buy) + f('pound_sell', 'الجنيه — بيع (اختياري)', p.pound_sell) + f('pound_buy', 'الجنيه — شراء (اختياري)', p.pound_buy) + f('sar_rate', 'سعر الريال السعودي بالريال اليمني', p.sar_rate) + f('usd_rate', 'سعر الدولار بالريال اليمني', p.usd_rate) +
        '<button class="btn g full" id="svP">حفظ الأسعار</button></div>' +
        '<div class="box"><h3>المساعد الذكي</h3><div class="sub">المفتاح يُحفظ في السيرفر فقط ولا يظهر في الموقع</div>' + f('api_key', 'مفتاح OpenAI', d.ai.api_key, 'text') + f('model', 'النموذج الأساسي', d.ai.model, 'text') + f('model_strong', 'نموذج اللحظات الحاسمة', d.ai.model_strong, 'text') + f('daily_cap_usd', 'السقف اليومي بالدولار', d.ai.daily_cap_usd) + f('monthly_cap_usd', 'السقف الشهري بالدولار', d.ai.monthly_cap_usd) +
        '<label class="chk"><input type="checkbox" id="aiOn"' + (d.ai.enabled ? ' checked' : '') + '><span>تشغيل المساعد في الموقع</span></label><button class="btn g full" id="svA">حفظ</button><button class="btn full" id="tsA" style="margin-top:10px">اختبار المساعد</button><div id="tsR" style="margin-top:12px;font-size:14px;line-height:1.9"></div></div></div>' +
        '<div class="g2"><div class="box"><h3>روابط التواصل</h3>' + f('l_tiktok', 'تيك توك', L.tiktok, 'text') + f('l_instagram', 'إنستغرام', L.instagram, 'text') + f('l_facebook', 'فيسبوك', L.facebook, 'text') + f('l_whatsapp', 'رقم واتساب (مع رمز الدولة)', L.whatsapp, 'text') + '<button class="btn g full" id="svL">حفظ الروابط</button></div>' +
        '<div class="box"><h3>حسابات التحويل</h3><div class="sub">تظهر للعميل فقط بعد موافقته على الشروط</div><div id="accs">' + (d.payments || []).map(acc).join('') + '</div><button class="btn s" id="addAcc">+ حساب</button> <button class="btn g s" id="svPay">حفظ الحسابات</button></div></div>' +
        '<div class="g2"><div class="box"><h3>سياسات المحل للمستشار الذكي</h3><div class="sub">يقرأها المستشار ويجاوب منها الزبون. اتركها فاضية إذا ما عندكم سياسة، وسيقول للزبون إن فريق المبيعات يوضحها.</div>' +
        ta('returns', 'الإرجاع والاستبدال', (d.policy || {}).returns) + ta('warranty', 'الضمان', (d.policy || {}).warranty) + ta('branches_near', 'معالم قرب كل فرع (مثلاً: فرع جرعان قريب من ...)', (d.policy || {}).branches_near) + ta('hours', 'أوقات الدوام', (d.policy || {}).hours) + ta('custom_orders', 'التفصيل حسب الطلب (تسوونه أو لا)', (d.policy || {}).custom_orders) + ta('pounds', 'بيع الجنيهات والسبائك (من الفرع فقط؟ متوفرة؟)', (d.policy || {}).pounds) + ta('other', 'معلومات أخرى يعرفها المستشار', (d.policy || {}).other) +
        '<button class="btn g full" id="svPol">حفظ السياسات</button></div>' +
        '<div class="box"><h3>بوت التليجرام</h3><div class="sub">الزبائن يكلمون نفس المستشار. وصاحب المحل يربط حسابه بإرسال: /admin ' + esc((d.telegram || {}).link_code || '') + ' للبوت، فيصير يكلم الوكيل الداخلي.</div>' +
        f('tg_token', 'رمز البوت من BotFather', (d.telegram || {}).token, 'text') +
        '<label class="chk"><input type="checkbox" id="tgOn"' + ((d.telegram || {}).enabled !== false ? ' checked' : '') + '><span>تشغيل البوت</span></label>' +
        '<div class="sub">الحالة: ' + esc((d.telegram || {}).status || '') + ((d.telegram || {}).username ? ' · @' + esc(d.telegram.username) : '') + ' · حسابات مربوطة: ' + ((d.telegram || {}).staff || 0) + '</div>' +
        '<button class="btn g full" id="svTg">حفظ</button></div></div>';
      $('#svP').onclick = function () { var b = {}; ['k21_sell', 'k21_buy', 'pound_sell', 'pound_buy', 'sar_rate', 'usd_rate'].forEach(function (k) { b[k] = parseFloat($('#f_' + k).value) || null }); api('/api/admin/prices', b).then(function () { toast('تم حفظ الأسعار') }).catch(function (e) { toast(e.error || 'خطأ') }) };
      $('#tsA').onclick = function () {
        var b = this; b.disabled = true; b.textContent = 'جاري الاختبار...';
        api('/api/admin/ai_test', {}).then(function (r) {
          $('#tsR').innerHTML = '<b style="color:' + (r.ok ? '#6fcf97' : '#eb5757') + '">' + esc(r.reason) + '</b>' + (r.results || []).map(function (x) { return '<div>' + (x.ok ? '✓ ' : '✗ ') + esc(x.model) + (x.ok ? '' : ' — ' + esc(x.why) + (x.code ? ' (' + x.code + ')' : '')) + '</div>' }).join('');
        }).catch(function (e) { $('#tsR').textContent = e.error || 'تعذر الاختبار' }).then(function () { b.disabled = false; b.textContent = 'اختبار المساعد' });
      };
      $('#svA').onclick = function () { api('/api/admin/settings', { ai: { api_key: $('#f_api_key').value, model: $('#f_model').value, model_strong: $('#f_model_strong').value, daily_cap_usd: parseFloat($('#f_daily_cap_usd').value), monthly_cap_usd: parseFloat($('#f_monthly_cap_usd').value), enabled: $('#aiOn').checked } }).then(function () { toast('تم الحفظ'); load() }).catch(function (e) { toast(e.error || 'خطأ') }) };
      $('#svL').onclick = function () { api('/api/admin/settings', { links: { tiktok: $('#f_l_tiktok').value, instagram: $('#f_l_instagram').value, facebook: $('#f_l_facebook').value, whatsapp: $('#f_l_whatsapp').value } }).then(function () { toast('تم الحفظ') }) };
      $('#addAcc').onclick = function () { $('#accs').insertAdjacentHTML('beforeend', acc({})) };
      $('#svTg').onclick = function () { api('/api/admin/settings', { telegram: { token: $('#f_tg_token').value, enabled: $('#tgOn').checked } }).then(function () { toast('تم الحفظ، البوت يشتغل خلال ثواني'); setTimeout(function () { settings(mp) }, 4000) }) };
      $('#svPol').onclick = function () { api('/api/admin/settings', { policy: { returns: $('#t_returns').value, warranty: $('#t_warranty').value, branches_near: $('#t_branches_near').value, hours: $('#t_hours').value, custom_orders: $('#t_custom_orders').value, pounds: $('#t_pounds').value, other: $('#t_other').value } }).then(function () { toast('تم الحفظ') }) };
      $('#svPay').onclick = function () { var list = $$('#accs .acc2').map(function (r) { return { name: $('[data-n]', r).value, holder: $('[data-h2]', r).value, account: $('[data-a]', r).value } }).filter(function (a) { return a.name && a.account }); api('/api/admin/settings', { payments: list }).then(function () { toast('تم الحفظ') }) };
    }).catch(err(mp));
    function f(k, l, v, t) { return '<label class="fld"><span>' + l + '</span><input class="inp' + (t ? '' : ' num') + '" id="f_' + k + '" type="' + (t || 'number') + '" value="' + esc(v == null ? '' : v) + '"></label>' }
    function acc(a) { return '<div class="acc2" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px"><input class="inp" data-n placeholder="البنك/المحفظة" value="' + esc(a.name || '') + '"><input class="inp" data-h2 placeholder="اسم صاحب الحساب" value="' + esc(a.holder || '') + '"><input class="inp num" data-a placeholder="رقم الحساب" value="' + esc(a.account || '') + '"></div>' }
  }
  function err(mp) { return function (e) { if (e && e.error) mp.innerHTML = '<div class="empty">' + esc(e.error) + '</div>' } }
  function boot() { api('/api/admin/me').then(function (me) { ME = me; if (me.role === 'accountant') TAB = 'requests'; shell(); load() }).catch(function () { }) }
  boot();
})();

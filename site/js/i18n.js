/* Arabic / English switch for the whole site. Arabic stays the source; English is applied on top of every text
   the page shows (including content the shop scripts render later), and removed again when switching back. */
(function () {
  var D = {
    "جم": "g", "كل": "All", "ر.ي": "YER", "بيع": "Sell", "ر.س": "SAR", "حلق": "Earrings", "طقم": "Set", "قطع": "Pieces", "سعر": "Price",
    "أطقم": "Sets", "شراء": "Buy", "الكل": "All", "عقود": "Necklaces", "صمّم": "Design", "تسوّق": "Shop", "باقتك": "your set",
    "سلاسل": "Chains", "الذهب": "Gold", "في إب": "in Ibb", "السعر": "Price", "أحزمة": "Belts", "أساور": "Bracelets", "الوضع": "Theme",
    "اليوم": "Today", "إرسال": "Send", "تواصل": "Contact", "القطع": "Pieces", "تصفية": "Filter", "الفئة": "Category", "الوزن": "Weight",
    "خواتم": "Rings", "بورصة": "Market", "إغلاق": "Close", "رسمية": "Official", "الفئات": "Categories", "شاهد ←": "View →",
    "فيسبوك": "Facebook", "راسلنا": "Message us", "قريباً": "Soon", "فروعنا": "Our branches", "المتجر": "Shop", "العيار": "Karat",
    "يومياً": "Daily", "واتساب": "WhatsApp", "مشابهة": "Similar", "الفروع": "Branches", "الأحدث": "Newest", "الترتيب": "Sort",
    "القائمة": "Menu", "خدماتنا": "Services", "تيك توك": "TikTok", "الخريطة": "Map", "إنستغرام": "Instagram", "عرض الكل": "View all",
    "الرئيسية": "Home", "المستشار": "Consultant", "اختياراتي": "My picks", "طقم العمر": "The set of a lifetime", "مساعد ذكي": "AI assistant",
    "المجموعات": "Collections", "تنسجم معها": "Pairs well with", "صمّم باقتك": "Design your set", "وصل حديثاً": "New arrival",
    "رقم القطعة": "Piece no.", "صُنع ليبقى": "Crafted to last", "ثلاثة فروع": "Three branches", "كل الأسعار": "All prices",
    "فروع في إب": "branches in Ibb", "قطعة مختارة": "Featured piece", "اكتب سؤالك…": "Type your question…", "أسعار الذهب": "Gold prices",
    "تصفية القطع": "Filter pieces", "شاهد القطعة": "View piece", "متوفرة الآن": "available now", "باقة العروس": "Bridal set",
    "احجز بعربون": "Reserve with deposit", "الفرع الأول": "Branch 1", "أسعار اليوم": "Today's prices", "بورصة الذهب": "Gold market",
    "وين فروعكم؟": "Where are your branches?", "ذهب عيار 21": "21K Gold", "حاسبة الذهب": "Gold calculator", "الجنيه الذهب": "Gold pound",
    "الفرع الثالث": "Branch 3", "يتكوّن أمامك": "takes shape before you", "الفرع الثاني": "Branch 2", "ساعدني أنسّق": "Help me match",
    "أطقم العرايس": "Bridal sets", "الوزن: الأخف": "Weight: lightest", "جمال المشرقي": "Gamal Almshrqi", "جرام عيار 21": "21K gram",
    "جم · عيار 21": "g · 21K", "مجموعة مميزة": "Signature", "تسوّق بالفئة": "Shop by category", "ساعدني أختار": "Help me choose",
    "جرعان": "Jar'an", "بجوار البوابة الرئيسية لمركز جرعان": "Next to the main gate of Jar'an Centre", "شاهد القطعة ←": "View piece →", "الوزن: الأثقل": "Weight: heaviest", "اسأل المستشار": "Ask our consultant",
    "مستشارك الخاص": "Your consultant", "عيار كل قطعنا": "karat, every piece", "ابحث عن قطعة…": "Search pieces…", "شاركها مع أحد": "Share it",
    "عيار 21 موثّق": "21K, documented", "شاهد كل القطع": "View all pieces", "عقود وكردانات": "Necklaces & collars", "أضف لاختياراتي": "Add to my picks",
    "الجنيه الذهب ·": "Gold pound ·", "جرام عيار 21 ·": "21K gram ·", "بتفاصيل تُورَث": "Made to be inherited", "تصفّح المجموعة": "Explore collection",
    "اكتشف التشكيلة": "Discover the collection", "تسوّق حسب الفئة": "Shop by category", "السعر: من الأقل": "Price: low to high",
    "سعر الذهب اليوم": "Today's gold price", "تحديث سعر الذهب": "gold price update", "10% لمدة 24 ساعة": "10% for 24 hours",
    "السعر: من الأعلى": "Price: high to low", "فاتورة برمز تحقق": "invoice with QR check", "استلام من المحل": "Pick up at our shop",
    "مستشار يرد فوراً": "Instant consultant", "سعر اليوم الشفاف": "Transparent pricing", "عقود بتكوين مركزي": "Centre-piece necklaces",
    "اسألني عن أي قطعة": "Ask me about any piece", "التفاصيل والحاسبة": "Details & calculator", "احجزها بعربون 10%": "Reserve with a 10% deposit",
    "اشترها بتحويل كامل": "Buy with a full transfer", "في الفاتورة الرسمية": "on the official invoice", "كم يسوى ذهبك اليوم؟": "What is your gold worth today?",
    "احفظها في اختياراتي": "Save to my picks", "مستشار جمال المشرقي": "Gamal Almshrqi consultant", "سياسة الحجز والشراء": "Reservation & purchase policy",
    "القيمة على سعر اليوم": "Value at today's price", "على الموقع والتليجرام": "on the site and Telegram", "الذهب والمصنعية واضحة": "gold and workmanship shown",
    "المجموع على سعر اليوم": "Total at today's price", "استفسر عنها على واتساب": "Ask about it on WhatsApp", "أرسل الباقة على واتساب": "Send the set on WhatsApp",
    "تنسيق متكامل ليوم العمر": "A complete wedding set", "الوزن بالجرام (عيار 21)": "Weight in grams (21K)", "عقد وحلق وكف وحزام، متناسقة.": "Necklace, earrings, hand piece and belt, all matching.",
    "الأسعار على سعر الذهب اليوم.": "Prices follow today's gold rate.", "إب — مركز جرعان — المحل رقم 6": "Ibb — Jar'an Centre — Shop 6",
    "جمال المشرقي للذهب والمجوهرات": "Gamal Almshrqi Gold & Jewelry", "اختر القطع من اليمين وتظهر هنا.": "Pick pieces and they appear here.",
    "شامل المصنعية · على سعر ذهب اليوم": "Including workmanship · at today's gold price", "الأسعار تتغير يومياً مع سعر الذهب": "Prices change daily with the gold rate",
    "متوفرة · تستلمها من الفرع اللي يريحك": "Available · pick up at the branch you prefer", "قطع تبني حضورها من الوسط، بنقش مرتب.": "Pieces built around a central motif, with orderly engraving.",
    "إب — بجوار البوابة الرئيسية لمركز جرعان": "Ibb — next to the main gate of Jar'an Centre", "جمال المشرقي للذهب والمجوهرات — محافظة إب.": "Gamal Almshrqi Gold & Jewelry — Ibb, Yemen.",
    "يظهر رسم السعر بعد تسجيل أسعار أكثر من يوم.": "The price chart appears once more than one day is recorded.",
    "إب — السبل — داخل ون مول": "Ibb — Al-Sabal, inside One Mall",
    "السبل — داخل ون مول": "Al-Sabal, inside One Mall",
    "صورة حقيقية للقطعة بدون أي تعديل": "Real, unedited photo of the piece",
    "تفاصيل قريبة": "Close-up",
    "مختارات المحل": "Shop's picks",
    "قطع يختارها المحل لك": "Pieces chosen by the shop",
    "أحدث ما وصل للمحل": "The latest to arrive",
    "عرض": "Display",
    "الصورة الحقيقية": "Real photo",
    "اختر قطعة أو أكثر من كل نوع، والمجموع يتحدّث على سعر اليوم.": "Pick one or more pieces of each kind; the total updates at today's price.",
    "هذه قيمة الذهب على سعر اليوم. عند شراء قطعة جديدة يُضاف إليها تكاليف المصنعية.": "This is the gold value at today's price. A new piece adds the cost of workmanship.",
    "أطقم العرايس والعقود والكردانات، بسعر ذهب اليوم شامل المصنعية، تستلمها من محلنا في إب.": "Bridal sets, necklaces and statement collars, priced at today's gold rate including workmanship. Pick up from our shop in Ibb.",
    "موقعنا": "Our location", "محلنا": "Our shop", "بجوار البوابة الرئيسية": "Next to the main gate", "الاستلام من المحل": "Pick up from the shop",
    "اختر العقد والحلق والكف والحزام قطعةً قطعة، وشاهد المجموع على سعر اليوم، ثم أرسلها لنا على واتساب.": "Choose the necklace, earrings, hand piece and belt one by one, see the total at today's price, then send it to us on WhatsApp.",
    "حياك الله في جمال المشرقي أنا مستشارك الخاص، أعرف كل قطعة متوفرة وسعرها اليوم. تجهّز لمناسبة، ولا تدور على شيء معيّن؟": "Welcome to Gamal Almshrqi. I'm your consultant and know every available piece and today's price. Preparing for an occasion, or looking for something specific?",
    "وصلتنا قطع جديدة هالأسبوع، تبغى أوريك أحلاها؟": "New pieces arrived this week. Shall I show you the best?",
    "وش أحدث القطع اللي وصلتكم؟": "What are your newest pieces?",
    "خلني أطلع لك أقوى التشكيلات اللي عندنا الحين": "Let me show you our strongest collections right now",
    "وريني أفخم التشكيلات عندكم": "Show me your finest collections",
    "تجهّز لعرس؟ أرتب لك طقم متكامل على ذوقك": "Preparing for a wedding? I'll put together a full set to your taste",
    "أبغى أجهز طقم عروس": "I want to put together a bridal set",
    "قل لي المناسبة والميزانية، وأرشّح لك الأنسب": "Tell me the occasion and budget, and I'll suggest the best fit",
    "محتار بين قطعتين؟ أقارن لك بينهم بصراحة": "Torn between two pieces? I'll compare them honestly",
    "أبغى أقارن بين قطعتين": "I want to compare two pieces",
    "تبي تعرف كم سعر قطعة على ذهب اليوم؟ اسألني": "Want a piece's price at today's gold rate? Ask me",
    "أبغى تنسيق متكامل": "I want a complete set", "قطع أخف": "Lighter pieces", "أبغى أكلم المبيعات": "I want to talk to sales",
    "عندكم أخف وزن؟": "Anything lighter?", "قطع مشابهة": "Similar pieces", "سعر الذهب اليوم": "Today's gold price",
    "عقد": "Necklace", "كف": "Hand piece", "حزام": "Belt", "خاتم": "Ring", "أسورة": "Bracelet", "سلسلة": "Chain", "كردان": "Collar",
    "محجوزة": "Reserved", "بيعت": "Sold", "حياك الله في جمال المشرقي": "Welcome to Gamal Almshrqi",
    "أنا مستشارك الخاص، أعرف كل قطعة متوفرة وسعرها اليوم. تجهّز لمناسبة، ولا تدور على شيء معيّن؟": "I'm your consultant and know every available piece and today's price. Preparing for an occasion, or looking for something specific?",
    "هذه القطعة بيعت أو لم تعد متاحة. شاهد القطع المتوفرة": "This piece has been sold or is no longer available. See available pieces"
  };
  var M = { "مليون": "M", "ألف": "K" };
  var P = [
    [/^(\d+) (قطع|قطعة)$/, function (m) { return m[1] + (m[1] === '1' ? ' piece' : ' pieces') }],
    [/^(\d+) · (.+)$/, function (m) { return m[1] + ' · ' + (D[m[2]] || m[2]) }],
    [/^▲ ([\d,.]+) عن أمس$/, function (m) { return '▲ ' + m[1] + ' vs yesterday' }],
    [/^▼ ([\d,.]+) عن أمس$/, function (m) { return '▼ ' + m[1] + ' vs yesterday' }],
    [/^حتى ([\d.]+) (مليون|ألف) ر\.ي$/, function (m) { return 'Up to ' + m[1] + M[m[2]] + ' YER' }],
    [/^أكثر من ([\d.]+) (مليون|ألف) ر\.ي$/, function (m) { return 'Over ' + m[1] + M[m[2]] + ' YER' }],
    [/^([\d.]+) (مليون|ألف) ر\.ي – ([\d.]+) (مليون|ألف) ر\.ي$/, function (m) { return m[1] + M[m[2]] + ' – ' + m[3] + M[m[4]] + ' YER' }],
    [/^([\d.]+) جرام · عيار (\d+)$/, function (m) { return m[1] + ' g · ' + m[2] + 'K' }],
    [/^عيار (\d+) · ([\d.]+) جرام$/, function (m) { return m[1] + 'K · ' + m[2] + ' g' }],
    [/^يحدّثها المحل يدوياً، آخر تحديث (.+)، وقد تتغير خلال اليوم\.$/, function (m) { return 'Updated by the shop; last update ' + m[1] + '. Prices may change during the day.' }]
  ];
  var ORIG = new WeakMap(), ATTR = new WeakMap(), LANG = 'ar', mo = null;
  function titles() { var S = window.GM_SITE; if (S && S.pieces) S.pieces.forEach(function (p) { if (p.title_en) D[p.title] = p.title_en }) }
  function tr(t) {
    var k = t.trim(); if (!k) return null;
    if (D[k]) return t.replace(k, D[k]);
    for (var i = 0; i < P.length; i++) { var m = k.match(P[i][0]); if (m) return t.replace(k, P[i][1](m)) }
    return null;
  }
  function apply(root) {
    var w = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT), n;
    while ((n = w.nextNode())) {
      if (n.parentElement && n.parentElement.closest('script,style,#msgs .me,[data-noi18n]')) continue;
      if (LANG === 'en') {
        if (!/[؀-ۿ]/.test(n.nodeValue)) continue;
        var v = tr(n.nodeValue); if (v != null) { ORIG.set(n, n.nodeValue); n.nodeValue = v }
      } else if (ORIG.has(n)) { n.nodeValue = ORIG.get(n); ORIG.delete(n) }
    }
    (root && root.querySelectorAll ? root : document).querySelectorAll('[placeholder],[aria-label]').forEach(function (e) {
      ['placeholder', 'aria-label'].forEach(function (a) {
        var v = e.getAttribute(a); if (!v) return;
        var store = ATTR.get(e) || {};
        if (LANG === 'en' && /[؀-ۿ]/.test(v)) { var x = tr(v); if (x != null) { store[a] = v; ATTR.set(e, store); e.setAttribute(a, x) } }
        else if (LANG === 'ar' && store[a]) { e.setAttribute(a, store[a]); delete store[a] }
      });
    });
  }
  function set(l) {
    LANG = l === 'en' ? 'en' : 'ar';
    try { localStorage.setItem('gm_lang', LANG) } catch (e) { }
    var h = document.documentElement; h.lang = LANG; h.dir = LANG === 'en' ? 'ltr' : 'rtl';
    document.querySelectorAll('[data-l]').forEach(function (b) { b.classList.toggle('on', b.dataset.l === LANG) });
    titles(); apply(document.body);
    if (mo) mo.disconnect();
    if (LANG === 'en') {
      mo = new MutationObserver(function (ms) {
        mo.disconnect();
        ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 3) { var v = tr(n.nodeValue); if (v != null) { ORIG.set(n, n.nodeValue); n.nodeValue = v } } else if (n.nodeType === 1) apply(n) }) });
        mo.observe(document.body, { childList: true, subtree: true });
      });
      mo.observe(document.body, { childList: true, subtree: true });
    }
    document.dispatchEvent(new Event('gm:lang'));
  }
  window.GM_lang = function () { return LANG };
  window.GM_tr = function (t) { return LANG === 'en' ? (tr(t) || t) : t };
  document.addEventListener('click', function (e) { var b = e.target.closest('[data-l]'); if (b) { e.preventDefault(); set(b.dataset.l) } });
  document.addEventListener('gm:ready', function () { titles(); if (LANG === 'en') apply(document.body) });
  var saved = 'ar'; try { saved = localStorage.getItem('gm_lang') || 'ar' } catch (e) { }
  if (saved === 'en') set('en');
})();

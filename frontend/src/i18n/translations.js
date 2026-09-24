/**
 * Every user-facing string, in Arabic and English.
 *
 * A plain object rather than react-i18next. This project has a habit of not
 * adding a dependency it does not need -- the HTML parser was removed, the
 * mail provider SDK was never added -- and a two-language site with a few
 * hundred strings needs a lookup table, not a framework with a plural engine
 * and a loader.
 *
 * ARABIC IS THE DEFAULT. The shoppers and the shop owners this is built for
 * read Arabic first; English is the second option, not the baseline.
 *
 * Prices stay in Latin digits in both languages. Jordanian price tags are
 * written 1045.50, not ١٠٤٥٫٥٠, and "localising" them would make the site
 * harder to read rather than more local.
 */

export const LOCALES = {
  ar: { label: 'العربية', short: 'ع', dir: 'rtl' },
  en: { label: 'English', short: 'EN', dir: 'ltr' },
};

export const DEFAULT_LOCALE = 'ar';

const translations = {
  ar: {
    // --- Brand and navigation
    'brand.name': 'احسن سعر',
    'brand.tagline': 'قارن الأسعار في الأردن',
    'nav.wishlist': 'المفضلة',
    'nav.alerts': 'التنبيهات',
    'nav.myShop': 'متجري',
    'nav.admin': 'الإدارة',
    'nav.account': 'حسابي',
    'nav.login': 'تسجيل الدخول',
    'nav.logout': 'خروج',
    'nav.toggleLanguage': 'English',
    'nav.toggleTheme': 'الوضع الليلي',
    'nav.toggleThemeLight': 'الوضع النهاري',
    'nav.menu': 'القائمة',
    'nav.closeMenu': 'إغلاق القائمة',

    // --- What a browser tab and a search engine read (hooks/useDocumentMeta)
    //
    // meta.siteTitle and meta.description in THIS table are index.html's
    // <title> and description, character for character, and a test holds
    // them together. Arabic is what a crawler gets -- it has no stored
    // locale -- so the head the server sends and the head the page sets once
    // it has rendered must say the same thing, or Google is shown two
    // descriptions of one URL and picks for itself.
    //
    // BOTH SPELLINGS OF THE NAME IN THE SITE TITLE. People search for the
    // Latin "Ahsan Se3r" as often as for the Arabic, and the Arabic name
    // alone is already shared with other sites; a title that carries only
    // one spelling cannot match the other search at all.
    //
    // The description is bilingual for the same reason and in the same order
    // as the page: Arabic first, because that is what shows when a result is
    // cut short.
    'meta.siteTitle': 'احسن سعر | Ahsan Se3r — قارن أسعار الإلكترونيات في الأردن',
    'meta.pageTitle': '{page} — احسن سعر',
    'meta.description':
      'قارن أسعار الهواتف واللابتوبات والشاشات بين متاجر الأردن، واعثر على المنتج الذي تريده بالضبط بأقل سعر. Compare phone, laptop and monitor prices across shops in Jordan and find the exact product you want at the lowest price.',
    'meta.results.title': 'أسعار «{query}»',
    'meta.results.description':
      'قارن أسعار «{query}» بين متاجر الأردن، من التطابق التام إلى المنتجات القريبة والمشابهة.',
    'meta.browse.description': '{category}: قارن الأسعار بين متاجر الأردن واعثر على أقل سعر.',
    'meta.product.titleFrom': '{name} ابتداءً من {price}',
    'meta.product.description': 'قارن أسعار {name} بين متاجر الأردن.',
    'meta.product.descriptionFrom': 'قارن أسعار {name} بين متاجر الأردن. جديد ابتداءً من {price}.',
    'meta.verifyEmail.title': 'تأكيد البريد الإلكتروني',

    // --- Home
    'home.title': 'قارن الأسعار في الأردن',
    'home.subtitle':
      'اكتب المنتج مع سعة التخزين واللون للحصول على تطابق دقيق.',
    'home.deals': 'أكبر التوفير الآن',
    'home.dealsHint': 'الفرق بين أرخص متجر وأغلى متجر',
    'home.save': 'وفّر',
    'home.at': 'من',
    'home.upTo': 'وتصل إلى',
    'home.elsewhere': 'في متاجر أخرى',
    'home.comparedAcross': 'مقارنة بين {count} متاجر',

    // --- Browsing the catalogue (home page, under the savings)
    'browse.title': 'تصفّح المتاجر',
    'browse.hint': 'أسعار حقيقية من متاجر أردنية',
    'browse.count': '{count} منتج',
    'category.phones': 'هواتف',
    'category.laptops': 'لابتوبات',
    'category.monitors': 'شاشات',
    'browse.showMore': 'عرض المزيد',
    'browse.showingOf': 'عرض {shown} من {total}',
    'browse.empty': 'لا توجد منتجات في هذا القسم بعد.',
    'browse.loadError': 'تعذّر تحميل المنتجات.',
    'browse.moreColours': 'متوفر بـ{count} ألوان أخرى',
    'browse.moreColoursOne': 'متوفر بلون آخر',

    // --- Search
    'search.placeholder': 'ابحث — اكتب سعة التخزين واللون',
    'search.button': 'بحث',
    'search.try': 'جرّب:',
    'search.results': '{count} منتج',
    'search.resultsOne': 'منتج واحد',
    'search.showingFor': 'نعرض نتائج «{corrected}»',
    'search.searchInstead': 'ابحث بدلاً من ذلك عن «{original}»',
    'search.suggestions': 'اقتراحات',
    'search.resultsFor': 'نتائج البحث عن «{query}»',
    'common.page': 'صفحة {page}',
    'search.counts': '({exact} مطابق · {close} قريب · {similar} مشابه)',
    'search.sortLabel': 'الترتيب داخل كل مجموعة',
    'search.sort.priceAsc': 'الأرخص أولاً',
    'search.sort.priceDesc': 'الأغلى أولاً',
    'search.sort.name': 'الاسم (أ–ي)',
    'search.empty': 'لا توجد نتائج لهذا البحث.',
    'search.emptyHint': 'جرّب اسم المنتج مع سعة التخزين، مثل «ايفون 15 128 جيجا».',
    'search.understood': 'فهمنا بحثك على أنه',
    'search.loadError': 'تعذّر تحميل النتائج.',
    'search.byName':
      'البحث بالاسم. أضف تفاصيل مثل سعة التخزين أو اللون — مثلاً «ايفون 15 128 جيجا أسود» — للحصول على تطابق دقيق.',
    'search.lookingFor': 'نبحث عن:',
    'search.ofTotal': '{shown} من {total}',
    'auth.linkSent': 'تم إرسال الرابط — تحقق من بريدك.',
    'auth.sending': 'جارٍ الإرسال…',

    // --- Match tiers
    'tier.exact': 'تطابق تام',
    'tier.exact.blurb': 'كل ما طلبته',
    'tier.close': 'قريب جداً',
    'tier.close.blurb': 'نفس المنتج، يختلف بتفصيل واحد',
    'tier.similar': 'منتجات مشابهة',
    'tier.similar.blurb': 'قريب، لكنه ليس ما بحثت عنه',
    'tier.matchPercent': '{score}٪ تطابق',
    'tier.nameMatch': 'مطابقة بالاسم',
    'tier.nameMatchTitle': 'وجدناه بالاسم أو الماركة — لم نتمكن من ترتيبه حسب المواصفات.',
    'tier.scoreTitle': 'درجة التطابق: {score}٪',

    // --- Why a match is not exact
    //
    // ONE KEY PER ATTRIBUTE, not one template with a {label} slot. Arabic
    // adjectives agree with their noun: it is "لون مختلف" but "ذاكرة مختلفة".
    // A single "{label} مختلف" template would be wrong on every feminine
    // attribute -- memory, resolution, variant, screen resolution -- and a
    // sentence that is grammatical half the time reads worse than English.
    'match.diff.brand.different': 'علامة تجارية مختلفة ({found} بدل {wanted})',
    'match.diff.brand.missing': 'العلامة التجارية غير مذكورة',
    'match.diff.model.different': 'طراز مختلف ({found} بدل {wanted})',
    'match.diff.model.missing': 'الطراز غير مذكور',
    'match.diff.variant.different': 'فئة مختلفة ({found} بدل {wanted})',
    'match.diff.variant.missing': 'الفئة غير مذكورة',
    'match.diff.storage.different': 'سعة تخزين مختلفة ({found} بدل {wanted})',
    'match.diff.storage.missing': 'سعة التخزين غير مذكورة',
    'match.diff.ram.different': 'ذاكرة مختلفة ({found} بدل {wanted})',
    'match.diff.ram.missing': 'الذاكرة غير مذكورة',
    'match.diff.color.different': 'لون مختلف ({found} بدل {wanted})',
    'match.diff.color.missing': 'اللون غير مذكور',
    'match.diff.cpu.different': 'معالج مختلف ({found} بدل {wanted})',
    'match.diff.cpu.missing': 'المعالج غير مذكور',
    'match.diff.size.different': 'حجم شاشة مختلف ({found} بدل {wanted})',
    'match.diff.size.missing': 'حجم الشاشة غير مذكور',
    'match.diff.resolution.different': 'دقة مختلفة ({found} بدل {wanted})',
    'match.diff.resolution.missing': 'الدقة غير مذكورة',
    'match.diff.refresh.different': 'معدل تحديث مختلف ({found} بدل {wanted})',
    'match.diff.refresh.missing': 'معدل التحديث غير مذكور',
    'match.diff.panel.different': 'نوع لوحة مختلف ({found} بدل {wanted})',
    'match.diff.panel.missing': 'نوع اللوحة غير مذكور',
    // Fallback for an attribute added to rules.py before this table caught
    // up. Ungendered on purpose -- "the X differs" needs no agreement -- so a
    // new attribute reads awkwardly rather than wrongly, and never as a raw
    // key on the page.
    'match.diff.different': 'يختلف في {label} ({found} بدل {wanted})',
    'match.diff.missing': 'غير مذكور: {label}',

    // --- Attribute names on their own, for the "we searched for" chips.
    // Separate from the match.diff.* phrases above because those are whole
    // sentences with the adjective already agreeing; these are bare nouns.
    'match.attr.brand': 'العلامة التجارية',
    'match.attr.model': 'الطراز',
    'match.attr.variant': 'الفئة',
    'match.attr.storage': 'سعة التخزين',
    'match.attr.ram': 'الذاكرة',
    'match.attr.color': 'اللون',
    'match.attr.cpu': 'المعالج',
    'match.attr.size': 'حجم الشاشة',
    'match.attr.resolution': 'الدقة',
    'match.attr.refresh': 'معدل التحديث',
    'match.attr.panel': 'نوع اللوحة',

    // --- Product photos
    'photo.label': 'صورة المنتج',
    'photo.hint': 'صورة واضحة للجهاز نفسه. JPG أو PNG أو WebP، حتى {mb} ميجابايت.',
    'photo.add': 'أضف صورة',
    'photo.change': 'تغيير الصورة',
    'photo.remove': 'حذف الصورة',
    'photo.uploadError': 'تعذّر رفع الصورة. حاول مرة أخرى.',
    'photo.errorType': 'اختر صورة بصيغة JPG أو PNG أو WebP.',
    'photo.errorSize': 'الصورة أكبر من {mb} ميجابايت.',
    // Refusals from the server, keyed by the code it sends. The server never
    // composes this sentence -- same contract as the match explanations.
    'photo.error.empty': 'الملف فارغ.',
    'photo.error.too_large': 'حجم الملف أكبر من المسموح.',
    'photo.error.svg': 'ملفات SVG غير مقبولة. ارفع صورة فوتوغرافية.',
    'photo.error.not_an_image': 'هذا الملف ليس صورة يمكن قراءتها.',
    'photo.error.unsupported_format': 'استخدم صورة بصيغة JPG أو PNG أو WebP.',
    'photo.error.too_many_pixels': 'دقة الصورة عالية جداً.',
    'product.noPhoto': 'لا توجد صورة',
    'common.networkError': 'تعذّر الوصول إلى الخادم.',

    // --- Attribute values worth saying in Arabic.
    //
    // Colours and variants only. Model codes, brands and capacities stay
    // Latin because that is how they are written on a Jordanian shelf and in
    // every Arabic-language listing we scrape -- "iPhone 15" and "128GB" are
    // not untranslated, they are the local spelling. Anything absent here
    // falls through to the raw value, so this table can never blank a word.
    'match.value.black': 'أسود',
    'match.value.white': 'أبيض',
    'match.value.silver': 'فضي',
    'match.value.gold': 'ذهبي',
    'match.value.blue': 'أزرق',
    'match.value.red': 'أحمر',
    'match.value.green': 'أخضر',
    'match.value.purple': 'بنفسجي',
    'match.value.pink': 'وردي',
    'match.value.yellow': 'أصفر',
    'match.value.orange': 'برتقالي',
    'match.value.gray': 'رمادي',
    'match.value.cream': 'كريمي',
    'match.value.mint': 'نعناعي',
    'match.value.beige': 'بيج',
    'match.value.graphite': 'جرافيت',
    'match.value.titanium': 'تيتانيوم',
    'match.value.starlight': 'ستارلايت',
    'match.value.lavender': 'لافندر',
    'match.value.midnight': 'ميدنايت',
    'match.value.rose_gold': 'ذهبي وردي',
    'match.value.space_gray': 'رمادي فلكي',
    'match.value.sierra_blue': 'أزرق سييرا',
    'match.value.pacific_blue': 'أزرق باسيفيك',
    'match.value.sky_blue': 'أزرق سماوي',
    'match.value.midnight_green': 'أخضر ميدنايت',
    'match.value.alpine_green': 'أخضر ألباين',
    'match.value.deep_purple': 'بنفسجي غامق',
    'match.value.natural_titanium': 'تيتانيوم طبيعي',
    'match.value.blue_titanium': 'تيتانيوم أزرق',
    'match.value.phantom_black': 'أسود فانتوم',
    'match.value.base': 'أساسي',
    'match.value.pro': 'برو',
    'match.value.pro_max': 'برو ماكس',
    'match.value.plus': 'بلس',
    'match.value.pro_plus': 'برو بلس',
    'match.value.ultra': 'ألترا',
    'match.value.mini': 'ميني',
    'match.value.max': 'ماكس',
    'match.value.air': 'إير',
    // Samsung's Fan Edition. Written FE on the box and in every Jordanian
    // listing; spelling it out in Arabic would name a thing nobody sells.
    'match.value.fe': 'FE',

    // --- Product page
    'product.back': 'رجوع للبحث',
    'product.new': 'جديد',
    'product.newFrom': 'جديد — ابتداءً من {price}',
    'product.used': 'مستعمل ومجدّد',
    'product.usedFrom': 'مستعمل ومجدّد — ابتداءً من {price}',
    'product.usedHint':
      'من متاجر محلية. تحقق من صحة البطارية وحالة الجهاز قبل الاتصال.',
    'product.noNewListings': 'لا يوجد متجر يعرض هذا المنتج جديداً حالياً.',
    'product.noListings': 'لا يوجد متجر يعرض هذا المنتج حالياً.',
    'product.history': 'سجل الأسعار',
    'product.notFound': 'هذا المنتج لم يعد موجوداً.',
    'product.loadError': 'تعذّر تحميل هذا المنتج.',

    // --- Price table
    'table.store': 'المتجر',
    'table.price': 'السعر',
    'table.delivery': 'التوصيل',
    'table.total': 'الإجمالي',
    'table.warranty': 'الكفالة',
    'table.availability': 'التوفر',
    'table.buy': 'الشراء',
    'table.bestDeal': 'أفضل سعر',
    'table.localShop': 'متجر محلي',
    'table.inStock': 'متوفر',
    'table.outOfStock': 'غير متوفر',
    'table.free': 'مجاني',
    'table.visit': 'زيارة',
    'table.months': '{count} شهر',
    'table.updated': 'حُدّث {age}',
    'table.stalePrice': 'آخر تأكيد للسعر {age} — تحقق قبل الشراء',
    'table.battery': 'البطارية {percent}٪',
    'table.hasDamage': 'يوجد ضرر',
    'table.noDamage': 'لا يوجد ضرر',

    // --- Time
    'time.today': 'اليوم',
    'time.yesterday': 'أمس',
    'time.daysAgo': 'قبل {count} يوم',
    'time.monthAgo': 'قبل شهر',
    'time.monthsAgo': 'قبل {count} أشهر',

    // --- Auth
    'auth.login': 'تسجيل الدخول',
    'auth.register': 'إنشاء حساب',
    'auth.email': 'البريد الإلكتروني',
    'auth.password': 'كلمة المرور',
    'auth.confirmPassword': 'تأكيد كلمة المرور',
    'auth.whatBringsYou': 'ما الذي جاء بك؟',
    'auth.iAmShopping': 'أنا أتسوّق',
    'auth.iAmShoppingBlurb': 'قارن الأسعار، احفظ المنتجات، واحصل على تنبيهات',
    'auth.iHaveShop': 'لدي متجر',
    'auth.iHaveShopBlurb': 'اعرض أسعارك ليجدك المتسوقون ويتصلوا بك',
    'auth.noAccount': 'ليس لديك حساب؟',
    'auth.haveAccount': 'لديك حساب؟',
    'auth.verifyBanner': 'أكّد بريدك الإلكتروني لتصلك تنبيهات الأسعار.',
    'auth.resendLink': 'إعادة إرسال الرابط',

    // --- Signing in with Google or Apple.
    // The failure keys carry the API's own error codes -- 'state_invalid',
    // not 'stateInvalid' -- because the callback looks the code up directly.
    // A code this table has not caught up with then surfaces as a visible
    // missing key rather than as a wrong but plausible sentence. And
    // email_unverified is the one failure a reader can actually fix, so it
    // names the fix instead of apologising.
    'auth.continueWithGoogle': 'المتابعة باستخدام Google',
    'auth.continueWithApple': 'تسجيل الدخول باستخدام Apple',
    'auth.or': 'أو',
    'auth.oauth.signingIn': 'جارٍ إتمام تسجيل الدخول…',
    'auth.oauth.problemTitle': 'تعذّر إتمام تسجيل الدخول',
    'auth.oauth.cancelledTitle': 'لم يكتمل تسجيل الدخول',
    'auth.oauth.state_invalid':
      'انتهت صلاحية محاولة الدخول أو استُخدمت من قبل. ابدأ من جديد.',
    'auth.oauth.unavailable':
      'تسجيل الدخول عبر Google أو Apple غير متاح الآن. يمكنك الدخول ببريدك الإلكتروني وكلمة المرور.',
    'auth.oauth.provider_error':
      'لم تكتمل الموافقة لدى المزوّد. إن كنت قد ألغيت العملية فهذا كل ما حدث — جرّب مرة أخرى أو ادخل ببريدك وكلمة المرور.',
    'auth.oauth.email_unverified':
      'لم يؤكّد المزوّد أن هذا البريد الإلكتروني لك. أكّد بريدك في إعدادات حسابك لدى Google أو Apple ثم أعد المحاولة، أو أنشئ حساباً ببريد وكلمة مرور هنا.',
    'auth.oauth.unknown':
      'لم يكتمل تسجيل الدخول. حاول مرة أخرى، أو ادخل ببريدك وكلمة المرور.',

    // --- The account page, and deleting an account.
    // The consequences are spelled out item by item rather than summarised as
    // "this cannot be undone", because the summary is the part everybody
    // already assumes and the items are the part nobody guesses: that a
    // support message keeps its text, that a shop is retired rather than
    // deleted, that its photographs go but its prices stay. A destructive
    // action behind a vague warning is a dark pattern, so the vague version
    // is not offered.
    'account.title': 'حسابك',
    'account.blurb': 'تفاصيل حسابك، وحذفه إن أردت.',
    'account.emailStatus': 'حالة البريد',
    'account.verified': 'مؤكَّد',
    'account.unverified': 'غير مؤكَّد',
    'account.unverifiedHint':
      'لا تُرسل تنبيهات الأسعار إلا إلى بريد مؤكَّد. استعمل الشريط في أعلى الصفحة لإرسال رابط جديد.',
    'account.role': 'نوع الحساب',
    'account.role.buyer': 'متسوّق',
    'account.role.merchant': 'تاجر',
    'account.role.admin': 'مشرف',
    'account.created': 'تاريخ الإنشاء',
    'account.limits':
      'لا توجد بعد صفحة لتغيير بريد الحساب أو لتنزيل نسخة من بياناتك. راسلنا وينفّذها شخص يدوياً.',
    'account.limitsLink': 'راسلنا',
    'account.delete.title': 'حذف الحساب',
    'account.delete.blurb':
      'الحذف نهائي: لا تراجع فيه، ولا نسخة محفوظة، ولا نستطيع إعادة حساب بعد حذفه.',
    'account.delete.start': 'أريد حذف حسابي',
    'account.delete.whatTitle': 'ماذا يحدث عند الحذف',
    'account.delete.goneTitle': 'يُحذف فوراً وبلا رجعة',
    'account.delete.gone.account':
      'حسابك وعنوان بريدك. ويصبح العنوان متاحاً للتسجيل من جديد في الحال.',
    'account.delete.gone.saved': 'كل ما حفظته: مفضّلتك وكل تنبيهات الأسعار.',
    'account.delete.gone.sessions':
      'كل جلسات الدخول على كل الأجهزة، بما فيها هذه الجلسة.',
    'account.delete.gone.social': 'أي ربط بحساب Google أو Apple.',
    'account.delete.keptTitle': 'يبقى بعد محو ما يدلّ عليك',
    'account.delete.kept.support':
      'رسائل الدعم التي أرسلتها يبقى نصّها ليبقى لدينا سجلّ المحادثة، لكن عنوان الردّ يُمحى فلا تعود الرسالة تدلّ عليك.',
    'account.delete.untouchedTitle': 'لا يتغيّر',
    'account.delete.untouched.taps':
      'عدّادات النقرات التي تُظهر لكل متجر كم متسوّقاً طلب رقمه. وهي مجهولة بالتصميم ولا تشير إلى أي شخص.',
    'account.delete.merchantTitle': 'إن كان لديك متجر',
    'account.delete.merchant.retired':
      'متجرك لا يُحذف مع الحساب بل يُعتزل: يُرفع عن الموقع فوراً، وتُمحى أرقام الهاتف والواتساب وروابط التواصل، ويُغيَّر اسمه — فأسماء المتاجر فريدة، ومتجر معتزل يحتفظ بالاسم يحجزه إلى الأبد ويمنع صاحب العمل من التسجيل به مرة أخرى.',
    'account.delete.merchant.photos':
      'كل صورة منتج رفعتها تُحذف. فهي من إنتاجك، وقد تُظهرك أو تُظهر محلّك، ولا يصحّ عرضها بعد اليوم.',
    'account.delete.merchant.listings':
      'أما العروض والأسعار وسجلّها فتبقى، لأنها جزء من كتالوج المنتجات الذي يقارنه المتسوّقون، لا جزء من حسابك.',
    'account.delete.merchantLink': 'راجع متجرك قبل الحذف',
    'account.delete.confirmTitle': 'اكتب بريدك الإلكتروني للتأكيد',
    'account.delete.confirmWhy':
      'بريدك لا كلمة المرور: الحساب المُنشأ عبر Google ليس له كلمة مرور أصلاً، والتأكيد لا بدّ أن يعمل له كذلك. ولا يهمّ حرف كبير ولا مسافة زائدة.',
    'account.delete.confirmLabel': 'بريدك الإلكتروني',
    'account.delete.confirm': 'احذف حسابي نهائياً',
    'account.delete.deleting': 'جارٍ الحذف…',
    'account.delete.mismatch': 'هذا ليس بريد هذا الحساب.',
    'account.delete.error': 'تعذّر حذف الحساب. حاول مرة أخرى.',
    'account.deleted.title': 'تم حذف حسابك.',
    'account.deleted.blurb':
      'زال كل ما ذُكر في صفحة الحساب. وعنوان بريدك متاح للتسجيل من جديد إن أردت العودة يوماً.',

    // --- Merchant
    'merchant.listYourShop': 'اعرض متجرك',
    'merchant.listYourShopBlurb':
      'أضف أسعارك ليراها المتسوقون في الأردن مع رقم هاتفك. مجاناً، ولا تحتاج موقعاً إلكترونياً.',
    'merchant.shopName': 'اسم المتجر',
    'merchant.shopNameHint':
      'هذا ما يراه المتسوقون. لا يمكن تغييره لاحقاً، فاستخدم الاسم الذي يعرفه زبائنك.',
    'merchant.phone': 'الهاتف',
    'merchant.whatsapp': 'واتساب',
    'merchant.facebook': 'صفحة فيسبوك',
    'merchant.instagram': 'انستغرام',
    'merchant.optional': '(اختياري)',
    'merchant.registerShop': 'تسجيل المتجر',
    'merchant.registering': 'جارٍ التسجيل…',
    'merchant.reviewNote':
      'نتحقق من كل متجر قبل نشر أسعاره، وقد يستغرق ذلك يوماً.',
    'merchant.verified': 'موثّق — أسعارك ظاهرة',
    'merchant.pending': 'قيد المراجعة — أسعارك غير ظاهرة بعد',
    'merchant.pendingNote':
      'يمكنك إضافة منتجاتك الآن. ستظهر في البحث فور تأكيد متجرك.',
    'merchant.contactHeading': 'كيف يصل إليك المتسوقون',
    'merchant.saveContact': 'حفظ بيانات التواصل',
    'merchant.saved': 'تم الحفظ',
    'merchant.addProduct': 'إضافة منتج',
    'merchant.productName': 'اسم المنتج',
    'merchant.priceJod': 'السعر (دينار)',
    'merchant.add': 'إضافة',
    'merchant.saving': 'جارٍ الحفظ…',
    'merchant.condition': 'الحالة',
    'merchant.conditionNew': 'جديد / مغلق',
    'merchant.conditionUsed': 'مستعمل',
    'merchant.conditionRefurbished': 'مجدّد',
    'merchant.usedNote':
      'يسأل المشترون عن هذه أولاً. لن يُقبل الإعلان بدونها.',
    'merchant.batteryHealth': 'صحة البطارية ٪',
    'merchant.warrantyMonths': 'الكفالة (أشهر)',
    'merchant.anyDamage': 'هل يوجد ضرر؟',
    'merchant.noDamage': 'لا يوجد ضرر',
    'merchant.yesDamage': 'نعم — سأصفه',
    'merchant.describeDamage': 'صف الضرر',
    'merchant.anythingElse': 'أي شيء آخر؟',
    'merchant.nameHint':
      'اكتب المنتج كما تقوله للزبون، مع سعة التخزين واللون. إضافة منتج تعرضه بنفس الحالة تحدّث سعره.',
    'merchant.yourProducts': 'منتجاتك',
    'merchant.noProducts': 'لم تضف أي منتج بعد. أضف أول منتج بالأعلى.',
    'merchant.notSearchable':
      'لا يظهر في البحث — لم نتعرف على هذا المنتج. جرّب كتابة الماركة والموديل وسعة التخزين.',
    'merchant.matchedTo': 'طوبق مع «{name}»',
    'merchant.notUpdatedSince': 'لم يُحدّث منذ {age} — يرى المتسوقون تنبيهاً',
    'merchant.remove': 'إزالة',
    'merchant.confirmRemove': 'إزالة «{name}» من متجرك؟ لا يمكن التراجع.',
    'merchant.save': 'حفظ',
    'merchant.productCount': '{count} منتج',
    'merchant.productCountOne': 'منتج واحد',
    // --- Contact taps -------------------------------------------------
    // TAPS, not calls. A tap is a shopper pressing Call or WhatsApp; whether
    // the phone rang or anyone bought anything happens off this platform.
    // The wording matters because a merchant is billed against this number.
    'stats.heading': 'وصول العملاء إليك',
    'stats.window': 'آخر {days} يوماً',
    'stats.taps': '{count} نقرة',
    'stats.tapsOne': 'نقرة واحدة',
    'stats.tapsNone': 'لا توجد نقرات بعد',
    'stats.call': 'اتصال',
    'stats.whatsapp': 'واتساب',
    'stats.facebook': 'فيسبوك',
    'stats.instagram': 'انستغرام',
    'stats.topProducts': 'الأكثر طلباً',
    'stats.explainer':
      'هذه نقرات على زر الاتصال أو واتساب — أي أن المتسوق طلب رقمك. لا نعرف إن تم الاتصال فعلاً أو تمت عملية بيع.',
    'stats.unverifiedHint': 'متجرك غير موثّق بعد، لذلك أسعارك لا تظهر للمتسوقين ولن تصلك نقرات.',
    'merchant.loadError': 'تعذّر تحميل متجرك.',

    // --- Added when the admin screen and the last English-only
    // surfaces were translated. The handoff had claimed for a while
    // that admin was the ONLY untranslated screen; it was not.
    'admin.title': 'لوحة التحكم',
    'admin.platform': 'المنصّة',
    'admin.merchantStores': 'متاجر التجار',
    'admin.merchantStoresBlurb': 'أسعار التاجر لا تظهر في البحث حتى يتم تأكيد طلبه. تأكّد أن الحساب يعود فعلاً للمتجر قبل القبول — أي شخص يستطيع التسجيل بأي اسم.',
    'admin.priceAnomalies': 'تغيّرات سعرية غير معتادة',
    'admin.users': 'المستخدمون ({count})',
    'admin.loading': 'جارٍ التحميل...',
    'admin.shop': 'المتجر',
    'admin.account': 'الحساب',
    'admin.contact': 'التواصل',
    'admin.listings': 'المنتجات',
    'admin.status': 'الحالة',
    'admin.taps': 'النقرات (٣٠ يوماً)',
    'admin.role': 'الدور',
    'admin.email': 'البريد الإلكتروني',
    'admin.id': 'الرقم',
    'admin.product': 'المنتج',
    'admin.was': 'كان',
    'admin.now': 'الآن',
    'admin.verified': 'موثّق',
    'admin.pending': 'قيد المراجعة',
    'admin.declined': 'مرفوض',
    'admin.emailUnconfirmed': 'بريد غير مؤكّد',
    'admin.approve': 'قبول',
    'admin.approveAnyway': 'قبول رغم الرفض',
    'admin.withdraw': 'سحب التوثيق',
    'admin.decline': 'رفض',
    'admin.delete': 'حذف',
    'admin.remove': 'إزالة',
    'admin.save': 'حفظ',
    'admin.change': 'تغيير',
    'admin.noShops': 'لم يسجّل أي متجر بعد.',
    'admin.shopHasNothing': 'هذا المتجر لم يضف أي منتج بعد.',
    'admin.noAnomalies': 'لم يتغيّر أي سعر بأكثر من ٥٠٪ خلال ٢٤ ساعة.',
    'admin.showListings': 'اعرض ما يبيعه هذا المتجر',
    'admin.emailUnconfirmedHint': 'هذا الحساب لم يؤكّد بريده الإلكتروني',
    'admin.tapsHint': 'متسوّقون ضغطوا على الاتصال أو واتساب أو فيسبوك. ليست مكالمات تمّت، وليست مبيعات.',
    'admin.stat.users': 'المستخدمون',
    'admin.stat.products': 'المنتجات',
    'admin.stat.stores': 'المتاجر',
    'admin.stat.aliases': 'عروض المتاجر',
    'admin.stat.prices': 'الأسعار الحالية',
    'admin.stat.history': 'سجلّ الأسعار',
    'admin.error.dashboard': 'تعذّر تحميل لوحة التحكم.',
    'admin.error.user': 'تعذّر حذف هذا المستخدم.',
    'admin.error.store': 'تعذّر تحديث هذا المتجر.',
    'admin.error.decline': 'تعذّر رفض هذا المتجر.',
    'admin.error.shopListings': 'تعذّر تحميل منتجات هذا المتجر.',
    'admin.error.listing': 'تعذّر تحديث هذا المنتج.',
    'admin.error.removeListing': 'تعذّر إزالة هذا المنتج.',
    'support.heading': 'رسائل التواصل',
    'support.unread': '{count} غير مقروءة',
    'support.showHandled': 'أظهر المعالَجة',
    'support.nothingWaiting': 'لا توجد رسائل بانتظارك.',
    'support.markHandled': 'تمّت المعالجة',
    'support.reopen': 'إعادة فتح',
    'support.noSubject': 'بدون عنوان',
    'support.account': '(الحساب: {email})',
    'support.loadError': 'تعذّر تحميل الرسائل.',
    'support.updateError': 'تعذّر تحديث هذه الرسالة.',
    'verify.confirmed': 'تم تأكيد بريدك',
    'verify.confirmedBlurb': 'تم تأكيد عنوانك. ستصلك الآن تنبيهات الأسعار.',
    'verify.linkFailed': 'هذا الرابط لم يعمل',
    'verify.linkFailedBlurb': 'قد يكون منتهي الصلاحية أو مستخدماً من قبل. الروابط تعمل مرة واحدة وتنتهي خلال ٢٤ ساعة.',
    'verify.signInAndResend': 'سجّل الدخول واستخدم «إعادة إرسال الرابط» للحصول على رابط جديد.',
    'alerts.title': 'تنبيهات الأسعار',
    'alerts.none': 'لا توجد تنبيهات بعد.',
    'alerts.noneBlurb': 'افتح منتجاً وحدّد سعراً مستهدفاً ليصلك تنبيه عند انخفاضه.',
    'alerts.targetReached': 'وصل السعر المطلوب — اشترِ الآن',
    'alerts.delete': 'حذف',
    'actions.alertSet': 'تم ضبط التنبيه',
    'actions.viewWishlist': 'عرض المفضلة',
    'actions.viewAlerts': 'عرض التنبيهات',
    'actions.tellMeBelow': 'أخبرني عندما ينزل عن',
    'auth.adminOnly': 'للمشرفين فقط',
    'auth.noAccess': 'حسابك لا يملك صلاحية الوصول لهذه الصفحة.',
    'common.startSearching': 'ابدأ البحث',
    'common.clickToChange': 'اضغط للتغيير',
    'common.facebookPage': 'صفحة فيسبوك',
    'common.priceFromShop': 'سعر أرسله المتجر',
    'common.priceHistoryByStore': 'سجلّ الأسعار حسب المتجر',
    'merchant.damageExample': 'خدش خفيف على الإطار، الشاشة سليمة',
    'merchant.notesExample': 'العلبة الأصلية والشاحن مرفقان',

    'merchant.saveError': 'تعذّر حفظ المنتج.',

    // --- Generic
    'common.loading': 'جارٍ التحميل…',
    'common.error': 'حدث خطأ',
    'common.notFound': 'الصفحة غير موجودة',
    'common.backHome': 'العودة للبحث',
    'common.stores': '{count} متاجر',
    'common.storeOne': 'متجر واحد',
    'common.notInStock': 'غير متوفر',
    'common.orUsedFrom': 'أو مستعمل من {price}',
    'common.usedOnly': 'مستعمل فقط',
    'common.inclDelivery': 'شامل التوصيل',
    'common.currency': 'دينار',
    'actions.save': 'حفظ',
    'actions.saved': 'محفوظ في المفضلة',
    'actions.saving': 'جارٍ الحفظ…',
    'actions.setAlert': 'تنبيه سعر',
    'actions.cancel': 'إلغاء',
    'actions.createAlert': 'إنشاء تنبيه',
    'actions.settingAlert': 'جارٍ الإنشاء…',
    'actions.saveError': 'تعذّر حفظ هذا المنتج.',
    'actions.alertError': 'تعذّر إنشاء التنبيه.',
    'actions.loginPrompt': 'سجّل الدخول لحفظ المنتج أو ضبط تنبيه سعر.',
    'chart.noHistory':
      'لا توجد تغييرات في السعر بعد. يتكوّن السجل عندما تغيّر المتاجر أسعارها بين عمليات التحديث.',
    'auth.forgotPassword': 'نسيت كلمة المرور؟',
    'auth.loggingIn': 'جارٍ الدخول…',
    'auth.invalidCredentials': 'البريد الإلكتروني أو كلمة المرور غير صحيحة.',
    'auth.forgotTitle': 'إعادة تعيين كلمة المرور',
    'auth.forgotBlurb':
      'اكتب بريدك الإلكتروني وسنرسل لك رابطاً لاختيار كلمة مرور جديدة.',
    'auth.sendResetLink': 'إرسال الرابط',
    'auth.resetSent':
      'إذا كان هناك حساب بهذا البريد، فقد أرسلنا إليه رابطاً. تحقق من بريدك.',
    'auth.resetTitle': 'اختر كلمة مرور جديدة',
    'auth.newPassword': 'كلمة المرور الجديدة',
    'auth.setPassword': 'حفظ كلمة المرور',
    'auth.resetDone': 'تم تغيير كلمة المرور. يمكنك تسجيل الدخول الآن.',
    'auth.resetInvalid': 'هذا الرابط غير صالح أو منتهي الصلاحية. اطلب رابطاً جديداً.',
    'auth.backToLogin': 'العودة لتسجيل الدخول',
    'auth.passwordsDoNotMatch': 'كلمتا المرور غير متطابقتين.',
    'nav.contact': 'اتصل بنا',
    'support.title': 'اتصل بنا',
    'support.blurb':
      'واجهت مشكلة أو لديك سؤال؟ اكتب لنا وسنرد على بريدك.',
    'support.yourEmail': 'بريدك الإلكتروني',
    'support.emailHint': 'سنرد على هذا العنوان.',
    'support.subject': 'الموضوع',
    'support.message': 'صف المشكلة',
    'support.send': 'إرسال',
    'support.sending': 'جارٍ الإرسال…',
    'support.sent': 'وصلتنا رسالتك. سنرد عليك قريباً.',
    'support.error': 'تعذّر إرسال الرسالة. حاول مرة أخرى.',
    'wishlist.title': 'المفضلة',
    'wishlist.empty': 'لم تحفظ أي منتج بعد.',
    'wishlist.emptyHint': 'ابحث عن منتج واضغط «حفظ» لمتابعة سعره.',
    'wishlist.remove': 'إزالة',
    'wishlist.loadError': 'تعذّر تحميل المفضلة.',
    'wishlist.from': 'ابتداءً من',
    'common.previous': 'السابق',
    'common.next': 'التالي',

    // --- Footer
    'footer.nav': 'روابط الموقع',
    'footer.notAShop':
      'نحن نقارن الأسعار فقط. لا نبيع شيئاً، ولا يتم أي شراء أو دفع على هذا الموقع.',
    'footer.about': 'من نحن',
    'footer.lab': 'كيف نطابق',
    'footer.privacy': 'الخصوصية',
    'footer.terms': 'الشروط',
    'footer.copyright': '© {year} احسن سعر',

    // --- About (pages/About.jsx)
    //
    // THE PAGE AN AI ASSISTANT QUOTES when someone asks what this site is, so
    // every sentence is a claim about the code, checked against it -- the
    // standard the privacy policy sets. "Several times a day", not "every six
    // hours": the interval is SCRAPE_INTERVAL_HOURS in deploy/.env, and a
    // number here would quietly become false the day it is changed.
    //
    // about.lead is also the Organization description in index.html's
    // structured data, and a test holds the two together.
    'about.metaTitle': 'من نحن',
    'about.title': 'عن احسن سعر',
    'about.lead':
      '«احسن سعر» (Ahsan Se3r) موقع أردني مجاني لمقارنة أسعار الهواتف واللابتوبات والشاشات بين المتاجر في الأردن.',
    'about.how.title': 'كيف يعمل',
    'about.how.sources':
      'نقرأ الأسعار من المتاجر الإلكترونية في الأردن عدة مرات في اليوم، وتضيف المحلات التي لا تملك موقعاً أسعارها بنفسها. لا تظهر أسعار أي محل قبل أن نتأكد أنه محل حقيقي.',
    'about.how.matching':
      'اكتب المنتج كما تريده بالضبط، مثل «iPhone 15 128GB Black». تظهر أولاً المطابقة التامة، ثم المنتجات القريبة والمشابهة، ولكل منها سبب اختلافه عمّا طلبت.',
    'about.how.used':
      'تُعرض الأجهزة المستعملة منفصلة، ولا تُقارن أبداً على أنها نسخة أرخص من الجديدة.',
    'about.buying.title': 'لا نبيع شيئاً',
    'about.buying.p1':
      'لا يتم أي شراء أو دفع على هذا الموقع. عندما تجد السعر المناسب، تشتري مباشرة من المتجر: من موقعه، أو بالاتصال به أو مراسلته على واتساب.',
    'about.buying.p2': 'البحث والمقارنة لا يحتاجان إلى حساب.',
    'about.shops.title': 'هل لديك محل؟',
    'about.shops.p1':
      'إذا كان لديك محل في الأردن يبيع هذه الأجهزة، يمكنك إنشاء حساب متجر وإضافة أسعارك، ليصل إليك الزبائن مباشرة بالاتصال أو على واتساب.',
    'about.shops.link': 'إنشاء حساب متجر',
    'about.how.lab': 'جرّبه بنفسك في مختبر المطابقة',
    'about.contact': 'لديك سؤال أو ملاحظة؟ راسلنا.',

    // --- The Matching Lab (pages/Lab.jsx)
    //
    // Brand and product names stay Latin, as everywhere else on the site:
    // "Pro+" and "Galaxy S24" are how they are written on a Jordanian shelf.
    'lab.metaTitle': 'مختبر المطابقة',
    'lab.title': 'مختبر المطابقة',
    'lab.lead':
      'اكتب بحثاً وأسماء المنتجات كما تكتبها المتاجر، وشاهد كيف يقرأ الموقع كل اسم — وكيف كان سيرتّبها «تشابه النصوص»، الطريقة المعتادة لمقارنة الأسماء.',
    'lab.examples': 'أمثلة',
    'lab.example.storage': 'حرف واحد، هاتف آخر',
    'lab.example.arabic': 'البحث بالعربية',
    'lab.example.case': 'الغطاء يحمل اسم الهاتف',
    'lab.example.plus': 'Pro+ ليس Pro',
    'lab.example.samsung': 'خطأ إملائي واسمان لهاتف واحد',
    'lab.example.laptop': 'لابتوبات',
    'lab.example.monitor': 'شاشات',
    'lab.exampleNote.storage':
      'المثال الذي بُني عليه الموقع: بين 128GB و256GB حرف واحد وهما هاتفان مختلفان، أما ترتيب الكلمات فتغيير كبير لا يغيّر شيئاً.',
    'lab.exampleNote.arabic':
      'تُوحَّد الإملاءات والأرقام العربية في الكلمات التي يقرؤها المحرك، و«Midnight» عند أبل هو اللون الأسود.',
    'lab.exampleNote.case':
      'الغطاء يكرّر اسم الهاتف حرفاً بحرف. تصنيف المتجر نفسه هو ما يقول إنه غطاء.',
    'lab.exampleNote.plus':
      'تكتب المتاجر الهاتف نفسه مع الماركة وبدونها، وعلامة «+» واحدة تفصل بين طرازين.',
    'lab.exampleNote.samsung':
      'يُصحَّح اسم الماركة المكتوب خطأً — ويُعرض التصحيح. و«Samsung S24» و«Galaxy S24» هاتف واحد.',
    'lab.exampleNote.laptop':
      'الفئات بيانات: اللابتوب يُقيَّم بالمعالج والتخزين والذاكرة، بأوزان خاصة به.',
    'lab.exampleNote.monitor':
      'حجم الشاشة ومعدل تحديثها أهم من الكلمات المشتركة مع البحث. والماركة شرط لا يُعوَّض.',
    'lab.exampleNote.custom': 'مثالك الخاص. اضغط «اشرح» لترى كيف يُقرأ.',
    'lab.form.query': 'البحث',
    'lab.form.listings': 'المنتجات كما تسمّيها المتاجر',
    'lab.form.categoryHint':
      'تصنيف المتجر اختياري، مثل «Mobile» أو «Mobile Case»، ويُقرأ تماماً كما يقرؤه الموقع.',
    'lab.form.title': 'المنتج {letter}',
    'lab.form.category': 'تصنيف المتجر',
    'lab.form.categoryLabel': 'تصنيف المتجر للمنتج {letter}',
    'lab.form.remove': 'حذف المنتج {letter}',
    'lab.form.add': 'إضافة منتج',
    'lab.form.full': 'الحد الأقصى {max} منتجات',
    'lab.form.submit': 'اشرح',
    'lab.form.dirty': 'تغيّر المثال — اضغط «اشرح» لتحديث النتيجة.',
    'lab.form.tooShort': 'اكتب {min} أحرف على الأقل في البحث.',
    'lab.form.noListings': 'أضف منتجاً واحداً على الأقل.',
    'lab.loading': 'جارٍ القراءة…',
    'lab.error': 'تعذّر شرح هذا البحث. حاول بعد قليل.',
    'lab.reading.title': 'كيف قُرئ البحث',
    'lab.reading.stage.typed': 'ما كتبته',
    'lab.reading.stage.spelling': 'بعد تصحيح الإملاء',
    'lab.reading.stage.arabic': 'العربية بكلمات المحرك',
    'lab.reading.stage.normalized': 'بعد التنظيف',
    'lab.reading.correction': 'قُرئت «{typed}» على أنها «{corrected}».',
    'lab.reading.understood': 'فُهم على أنه',
    'lab.reading.unread':
      'لا يذكر هذا البحث شيئاً يستطيع المحرك قراءته، فيبحث الموقع بالاسم فقط ولا يوجد ما يُقيَّم.',
    'lab.rank.title': 'طريقتان لترتيب المنتجات نفسها',
    'lab.rank.similarity': 'تشابه النصوص',
    'lab.rank.similarityHint': 'كم حرفاً تشترك فيه الأسماء',
    'lab.rank.engine': 'هذا الموقع',
    'lab.rank.engineHint': 'أيّ المواصفات تتطابق',
    'lab.rank.headline':
      'يضع تشابه النصوص {worseLetter} «{worse}» فوق {betterLetter} «{better}»: {worseSimilarity} مقابل {betterSimilarity}. أما هذا الموقع فيعطيهما {worseScore} و{betterScore}، والسبب: {reason}.',
    'lab.rank.headlineTie':
      'لا يستطيع تشابه النصوص التمييز بين {worseLetter} «{worse}» و{betterLetter} «{better}»: كلاهما {betterSimilarity}. أما هذا الموقع فيعطيهما {worseScore} و{betterScore}، والسبب: {reason}.',
    'lab.rank.headlineUnscored':
      'يضع تشابه النصوص {worseLetter} «{worse}» فوق {betterLetter} «{better}»: {worseSimilarity} مقابل {betterSimilarity}. أما هذا الموقع فيعطي {betterLetter} {betterScore} ولا يقيّم {worseLetter} أصلاً: {reason}.',
    'lab.rank.headlineTieUnscored':
      'لا يستطيع تشابه النصوص التمييز بين {worseLetter} «{worse}» و{betterLetter} «{better}»: كلاهما {betterSimilarity}. أما هذا الموقع فيعطي {betterLetter} {betterScore} ولا يقيّم {worseLetter} أصلاً: {reason}.',
    'lab.rank.agree': 'هنا تتفق الطريقتان على الترتيب، لكن واحدة منهما فقط تستطيع أن تقول لماذا.',
    'lab.rank.pairs':
      '{against} من {total} أزواج مرتّبة بعكس ترتيب الموقع، أو متعادلة حيث يرى الموقع فرقاً.',
    'lab.short.gated': 'ماركة أخرى',
    'lab.short.other_category': 'نوع آخر',
    'lab.short.nothing_to_score': 'بلا درجة',
    'lab.short.refused_by_store': 'مرفوض',
    'lab.short.unrecognised': 'غير مقروء',
    'lab.short.query_unread': 'بلا درجة',
    'lab.reason.refused_by_store': 'المتجر يصنّفه تحت «{category}»، وهي ليست فئة يعرضها الموقع',
    'lab.reason.other_category': 'إنه نوع آخر من المنتجات',
    'lab.reason.nothing_to_score': 'البحث يذكر الماركة فقط',
    'lab.reason.unrecognised': 'ليس هاتفاً أو لابتوب أو شاشة يستطيع المحرك قراءتها',
    'lab.reason.query_unread': 'البحث لا يذكر شيئاً يستطيع المحرك قراءته',
    'lab.outcome.gated': 'الماركة شرط: {reason}. يُستبعد مهما تطابق غيرها.',
    'lab.outcome.refused_by_store':
      'يصنّفه المتجر تحت «{category}». آخر كلمة في تصنيف المتجر تقول ما هو الشيء، وهذا ليس هاتفاً أو لابتوب أو شاشة — فلا يدخل الكتالوج مهما قال عنوانه.',
    'lab.outcome.other_category':
      'قُرئ على أنه من فئة {found} والبحث عن {wanted}. لا يُقارَن نوعان مختلفان من المنتجات أبداً.',
    'lab.outcome.nothing_to_score':
      'البحث يذكر الماركة فقط، فلا يوجد ما يُقيَّم. في الموقع تظهر منتجات كهذه دون ترتيب كمطابقة بالاسم.',
    'lab.outcome.unrecognised':
      'لم يُتعرَّف عليه كهاتف أو لابتوب أو شاشة، فلن يدخل الكتالوج.',
    'lab.outcome.query_unread': 'البحث لا يذكر شيئاً يستطيع المحرك قراءته، فلا يُقيَّم هذا المنتج.',
    'lab.listSeparator': '، ',
    'lab.tier.exact': 'تطابق تام',
    'lab.tier.close': 'قريب جداً',
    'lab.tier.similar': 'مشابه',
    'lab.tier.excluded': 'لا يظهر',
    'lab.cards.title': 'الدرجات بالتفصيل',
    'lab.weights.lead':
      '{category}: يبدأ كل منتج من 100، ويخسر وزن كل مواصفة طلبها البحث ولم يجدها. المواصفة التي لم يذكرها البحث لا تكلّف شيئاً.',
    'lab.weights.barLabel': 'أوزان المواصفات، ومجموعها 100',
    'lab.weights.gate':
      'لا تُحسب بالنقاط لأنها شرط: {attributes}. إذا اختلفت يُستبعد المنتج مهما تطابق غيرها.',
    'lab.legend.kept': 'تطابقت — تبقى النقاط',
    'lab.legend.lost': 'اختلفت — يُخصم وزنها',
    'lab.legend.unasked': 'ليست في البحث — لا تكلّف شيئاً',
    'lab.ladder':
      'الفئات: 100 تطابق تام · من 85 قريب جداً · من 70 مشابه · وما دون 70 لا يظهر في البحث.',
    'lab.bar.label': 'الدرجة {score} من 100',
    'lab.bar.keptTitle': '{name}: {value} — تبقى {weight} نقطة',
    'lab.bar.lostTitle': '{name}: {found} بدل {wanted} — تُخصم {weight} نقطة',
    'lab.bar.unaskedTitle': '{name}: ليست في البحث، لا تكلّف شيئاً',
    'lab.bar.notStated': 'غير مذكور',
    'lab.card.storeCategory': 'تصنيف المتجر:',
    'lab.card.read': 'قُرئ على أنه',
    'lab.card.allKept': 'كل ما طلبه البحث موجود.',
    'lab.card.unasked': 'ليست في البحث، فلا تكلّف شيئاً: {attributes}',
    'lab.card.ranks':
      'تشابه النصوص {similarity}، المرتبة {similarityRank} من {total} هناك، و{engineRank} هنا.',
    'lab.honest':
      'لا شيء في هذه الصفحة محاكاة: يُرسَل نصك إلى الشيفرة نفسها التي يشغّلها البحث، ولا يُحفظ شيء.',
    'lab.similarityExplained':
      'يحصل تشابه النصوص هنا على النص المنظَّف نفسه الذي يقرؤه المحرك — أحرف صغيرة، دون علامات ترقيم، والعربية موحّدة — فالفرق الوحيد بين العمودين هو طريقة الترتيب.',
    'lab.aboutLink': 'عن احسن سعر',

    // --- Legal pages: the furniture both of them share
    // The two blanks are deliberately loud. A privacy policy that ships with
    // "[company name]" inside a paragraph is worse than no policy at all --
    // it reads as boilerplate nobody checked -- so the unfilled fields get a
    // panel at the top of the page rather than a marker buried in a sentence.
    'legal.updated': 'آخر تحديث: أيلول 2026',
    'legal.contents': 'في هذه الصفحة',
    'legal.todo.title': 'هذه الصفحة لم تُستكمل بعد',
    'legal.todo.blurb': 'على مشغّل الموقع تعبئة ما يلي قبل النشر:',
    'legal.todo.blank': '⟨ يُملأ ⟩',
    'legal.field.entity': 'الاسم القانوني للجهة التي تشغّل هذا الموقع',
    'legal.field.dataContact':
      'عنوان البريد الإلكتروني لطلبات البيانات: الاطّلاع والتصحيح والحذف',
    'legal.field.law': 'الدولة التي تحكم قوانينها هذه الشروط',

    // The operator's own details. Paired with the legal.field.* labels above:
    // LegalPage renders the value where the blank was, and the amber "this
    // page is not finished" panel goes quiet once all three are filled. Both
    // pages point here -- "الجهة المشغّلة مذكورة في أعلى هذه الصفحة" -- so
    // emptying one of these makes those sentences false again.
    'legal.value.entity': 'سالم أسعد محمود مصطفى',
    'legal.value.dataContact': 'altamarysalem@gmail.com',
    'legal.value.law': 'الأردن',

    // --- Privacy policy
    // Every sentence here is a claim about what this code does, and the ones
    // the code did not back were cut rather than softened. There is no
    // scheduled purge anywhere in the backend, so the page promises no
    // retention period; product images really are fetched by the shopper's
    // browser from the retailers' own servers, so the page says so instead
    // of claiming nothing leaves the site.
    'privacy.title': 'سياسة الخصوصية',
    'privacy.blurb': 'ما الذي نحفظه عنك، ولماذا، ومن يراه غيرنا.',

    'privacy.who.title': 'من يشغّل هذا الموقع',
    'privacy.who.p1':
      '«احسن سعر» موقع لمقارنة أسعار الأجهزة في المتاجر الأردنية. الجهة المشغّلة مذكورة في أعلى هذه الصفحة، وهي المسؤولة عن كل ما يرد هنا.',
    'privacy.who.p2':
      'نتعامل مع بياناتك وفق قانون حماية البيانات الشخصية الأردني رقم 24 لسنة 2023.',
    'privacy.who.p3':
      'كتبنا هذه الصفحة بلغة واضحة قدر ما استطعنا. إن بقي فيها ما هو غامض، راسلنا وسنشرحه.',

    'privacy.collect.title': 'ما الذي نجمعه',
    'privacy.collect.intro': 'لا نجمع إلا ما تحتاجه الخدمة فعلاً:',
    'privacy.collect.account':
      'الحساب: بريدك الإلكتروني، وكلمة المرور محفوظة كبصمة مشفّرة لا يمكن الرجوع منها إلى الكلمة نفسها، ونوع الحساب، وتاريخ إنشائه، وما إذا كنت قد أكّدت بريدك.',
    'privacy.collect.noProfile':
      'لا نطلب اسمك ولا رقمك ولا عنوانك ولا تاريخ ميلادك. ولا توجد وسيلة دفع على الموقع، فلا نملك أي بيانات بطاقة.',
    'privacy.collect.shop':
      'إن كان لديك متجر: اسم المتجر وموقعه وشعاره، وبيانات التواصل التي تختار نشرها — الهاتف وواتساب وفيسبوك وانستغرام. هذه تظهر لكل زائر على صفحة المنتج.',
    'privacy.collect.listing':
      'تفاصيل العروض التي يكتبها التاجر: الحالة، ونسبة البطارية، ووصف أي ضرر، ومدة الكفالة، والملاحظات. تُنشر كما كُتبت.',
    'privacy.collect.photos':
      'صور العروض التي يرفعها التاجر. تُحفظ كصورة فقط: نعيد ترميزها بالكامل، فلا يبقى فيها موقع التقاط ولا رقم جهاز ولا وقت تصوير.',
    'privacy.collect.wishlist':
      'المفضلة وتنبيهات السعر: أي منتج حفظته، وعند أي سعر تريد أن نخبرك.',
    'privacy.collect.support':
      'رسائل الدعم: البريد الذي تكتبه في النموذج، والموضوع، ونص الرسالة.',
    'privacy.collect.sessions':
      'سجلّ الدخول: متى بدأت كل جلسة ومتى انتهت. ويكتب الخادم في سجلّاته عنوان الـ IP ورقم الحساب عند تسجيل الدخول وإنشاء الحساب وإعادة تعيين كلمة المرور.',
    'privacy.collect.provider':
      'إذا دخلت عبر جوجل أو آبل: نخزّن معرّفاً دائماً يعطينا إيّاه المزوّد، وعنوان بريدك. لا نطلب اسمك ولا صورتك ولا نستلمهما — الصلاحية التي نطلبها هي البريد وحده.',
    'privacy.collect.linkPassword':
      'وإن كان على البريد نفسه حساب بكلمة مرور لم يُؤكَّد بريده بعد، فإن الدخول عبر المزوّد يربط الاثنين ويُلغي كلمة المرور القديمة وينهي جلساتها. السبب أن تلك الكلمة وضعها شخص لم يُثبت يوماً أنه يملك هذا البريد. تستطيع وضع كلمة مرور جديدة من «نسيت كلمة المرور».',

    'privacy.why.title': 'لماذا نحتفظ بها',
    'privacy.why.signin': 'لتسجيل دخولك وإبقائك داخل حسابك بعد تحديث الصفحة.',
    'privacy.why.alerts':
      'لإرسال تنبيه حين ينزل سعر منتج تتابعه، ولإرسال روابط تأكيد البريد وإعادة تعيين كلمة المرور.',
    'privacy.why.shop': 'لعرض بيانات المتجر للمتسوّق كي يستطيع التواصل معه.',
    'privacy.why.support': 'للرد على رسائلك.',
    'privacy.why.abuse':
      'لحماية الموقع: نعدّ المحاولات القادمة من كل عنوان كي لا تُخمّن كلمات المرور بالتكرار.',
    'privacy.why.noSale':
      'لا نبيع بياناتك ولا نؤجّرها ولا نستخدمها لإعلانات، ولا يوجد على الموقع أي شبكة إعلانات.',

    'privacy.not.title': 'ما لا نجمعه، عن قصد',
    'privacy.not.intro': 'هذه قرارات في بناء الموقع، لا أشياء نسيناها:',
    'privacy.not.analytics':
      'لا يوجد أي نظام تحليلات أو تتبّع خارجي، ولا بكسل إعلاني، ولا تسجيل لجلسات التصفّح. لا يُحمَّل على هذا الموقع شيء من شركة تحليلات.',
    'privacy.not.search':
      'لا نحتفظ بسجلّ لما بحثت عنه. نص البحث يصل إلى الذاكرة المؤقتة على شكل بصمة غير قابلة للقراءة، وتُمحى بعد خمس دقائق.',
    'privacy.not.taps':
      'حين تضغط «اتصال» أو «واتساب» نسجّل أربعة أشياء فقط: أي متجر، وأي منتج، وأي قناة، ومتى. بلا عنوان IP، وبلا رقم حساب، وبلا معرّف جلسة.',
    'privacy.not.exif':
      'لا نحتفظ بالبيانات المخفيّة داخل الصور. كل صورة مرفوعة تُفكّ وتُكتب من جديد، فيختفي معها موقع الالتقاط ونوع الجهاز ووقت التصوير.',
    'privacy.not.sensors':
      'لا نطلب موقعك ولا الكاميرا ولا الميكروفون، والموقع يخبر متصفّحك صراحةً أن يرفض هذه الطلبات.',
    'privacy.not.tapsWhy':
      'نعدّ النقرات لأن التاجر يحتاج أن يعرف إن كان الموقع يفيده. والثمن الذي قبلناه مقابل ألّا نسجّل هويّتك أننا لا نميّز بين شخصين: من يضغط مرتين يُحسب نقرتين. لذلك نقول «نقرات» ولا نقول «اتصالات» ولا «مبيعات» — نحن لا نعرفها.',

    'privacy.cookies.title': 'الكوكيز والتخزين في متصفّحك',
    'privacy.cookies.one':
      'نضع كوكي واحداً فقط، اسمه refresh_token، ولا يوضع إلا بعد تسجيل دخولك. وظيفته الوحيدة أن تبقى داخل حسابك بعد تحديث الصفحة. لا يستطيع أي كود في الصفحة قراءته، ولا يُرسل إلا إلى مسار الدخول، ومدّته سبعة أيام، ويُحذف عند الخروج.',
    'privacy.cookies.local':
      'ويحفظ متصفّحك شيئين اخترتهما أنت بالضغط: اللغة، والوضع الليلي أو النهاري. يبقيان على جهازك ولا يصلان إلى خادمنا أبداً.',
    'privacy.cookies.oauth':
      'وكوكي ثانٍ قصير العمر يُنشأ فقط عند بدء الدخول عبر جوجل أو آبل ويُحذف فور انتهائه. مهمّته أن يُثبت أن الجلسة العائدة هي التي بدأها متصفّحك أنت لا متصفّح شخص آخر، وعمره عشر دقائق.',
    'privacy.cookies.noBanner1': 'ولهذا لا ترى هنا نافذة موافقة على الكوكيز.',
    'privacy.cookies.noBanner2':
      'الكوكي الوحيد ضروري لتسجيل الدخول، والموافقة لا تُطلب على ما هو ضروري لأداء الخدمة. أما اللغة والوضع فاختيارك أنت، ولا يحملان أي معرّف، ولا يغادران جهازك. ولا يوجد شيء ثالث نتتبّعك به.',
    'privacy.cookies.noBanner3':
      'نافذة موافقة هنا ستوحي بتتبّع لا يحدث، وستدرّبك على الضغط «موافق» دون قراءة. إن أضفنا يوماً ما يتتبّعك فعلاً، سنسألك قبله.',

    'privacy.others.title': 'من يرى شيئاً غيرنا',
    'privacy.others.intro': 'نحاول أن تكون هذه القائمة أقصر ما يمكن، لكنها ليست فارغة:',
    'privacy.others.images':
      'صور المنتجات تأتي من خوادم المتاجر نفسها، ومتصفّحك يجلبها منهم مباشرة. أي أن المتجر — وشركة الاستضافة التي يستعملها — يرى عنوان الـ IP الخاص بك ونوع متصفّحك. هذه أهم نقطة في هذه الصفحة.',
    'privacy.others.referrer':
      'نطلب من متصفّحك ألّا يخبرهم بالصفحة التي كنت فيها، فلا يعرفون أي منتج كنت تنظر إليه. لكن عنوان الـ IP لا يمكن إخفاؤه ما دمنا نعرض صورهم.',
    'privacy.others.meta':
      'أزرار واتساب وفيسبوك وانستغرام تنقلك إلى شركة ميتا. ما يحدث بعد الضغط تحكمه سياساتها لا سياستنا.',
    'privacy.others.email':
      'بريدنا — التأكيد وإعادة تعيين كلمة المرور وتنبيهات السعر والرد على الدعم — يمرّ عبر مزوّد البريد Brevo، الذي يرى عنوانك ونص الرسالة. ويستبدل Brevo الروابط داخل الرسائل بروابط تمرّ عبره أولاً ليعرف أنها فُتحت، ولا تسمح خطتنا الحالية بإيقاف ذلك. لهذا نجعل روابط إعادة تعيين كلمة المرور تنتهي خلال ساعة واحدة.',
    'privacy.others.hosting':
      'قاعدة البيانات والذاكرة المؤقتة وسجلّات الخادم تعمل عند مزوّدي استضافة، وهم قادرون تقنياً على الوصول إليها بحكم تشغيلهم لها.',
    'privacy.others.providers':
      'زر «المتابعة بجوجل» أو «الدخول بآبل» ينقل متصفّحك إلى جوجل أو آبل، ثم يتبادل خادمنا معهم رمزاً للتحقق من هويتك. هذا لا يحدث إلا لمن يضغط الزر: الزائر الذي يقارن الأسعار فقط لا يصل منه إليهما شيء.',
    'privacy.others.fonts':
      'الخطوط وبقية ملفات الموقع كلها من خادمنا، فلا يُحمَّل أي خط من خطوط جوجل ولا من أي شبكة توزيع خارجية. وهذا يخص الملفات وحدها: إن اخترت الدخول بجوجل فجوجل طرف في ذلك، كما هو مذكور أعلاه.',
    'privacy.others.retailers':
      'أسعار المتاجر التي نقرأها آلياً يجلبها خادمنا على فترات، لا متصفّحك. زيارتك أنت لا تصل إليهم منّا.',

    'privacy.keep.title': 'كم من الوقت نحتفظ بها',
    'privacy.keep.honest':
      'بصراحة: لا يوجد حتى الآن حذف تلقائي. أغلب السجلات تبقى إلى أن تحذفها أنت أو نحذفها نحن يدوياً عند طلبك. لا نعدك بمدّة لا ينفّذها الكود.',
    'privacy.keep.wishlist': 'المفضلة وتنبيهات السعر: تبقى إلى أن تحذفها أو يُحذف حسابك.',
    'privacy.keep.links':
      'روابط البريد: رابط التأكيد ينتهي خلال أربع وعشرين ساعة، ورابط إعادة تعيين كلمة المرور خلال ساعة واحدة، وكلاهما يعمل مرة واحدة فقط. ويبقى سجلّ بأن رابطاً قد أُرسل.',
    'privacy.keep.sessions':
      'جلسات الدخول: تنتهي صلاحيتها بعد سبعة أيام، ويبقى سجلّ بأن جلسة بدأت وانتهت.',
    'privacy.keep.support':
      'رسائل الدعم: يبقى نصّها حتى بعد حذف الحساب، لأن الرسالة هي ما يفسّر لماذا فعلنا شيئاً. أما عنوان بريدك فيها فيُستبدل عند الحذف.',
    'privacy.keep.prices': 'سجلّ الأسعار يبقى بلا حدّ، لكنه عن المنتجات لا عن الأشخاص.',
    'privacy.keep.logs':
      'سجلّات الخادم تحتفظ بها جهة الاستضافة حسب إعداداتها، ولا يوجد في الكود ما يحذفها بعد مدة معيّنة.',

    'privacy.rights.title': 'حقوقك، وكيف تستعملها',
    'privacy.rights.intro':
      'بموجب قانون حماية البيانات الشخصية رقم 24 لسنة 2023، يحقّ لك أن تعرف ما نحفظه عنك، وأن تصحّحه، وأن تطلب حذفه، وأن تعترض على استخدامه.',
    'privacy.rights.delete':
      'حذف الحساب: من صفحة حسابك، وهو نهائي ولا رجعة فيه. يزيل الحذف حسابك وجلسات دخولك وروابطك المؤقتة ومفضّلتك وتنبيهاتك. وإن كنت تاجراً، يُرفع متجرك عن الموقع ويُمحى اسمه وبيانات تواصله، وتُحذف صور عروضك.',
    'privacy.rights.providerLink':
      'ارتباطك بجوجل أو آبل: حذف حسابك يزيله من عندنا. لكن الإذن الذي أعطيته يبقى في حسابك عندهم، فاحذف هذا الموقع من إعدادات حسابك في جوجل أو آبل إن أردت قطع الصلة تماماً.',
    'privacy.rights.survives':
      'ما يبقى بعد الحذف: نصّ رسائل الدعم التي أرسلتها، بعد استبدال عنوان بريدك فيها برمز لا يُقرأ منه العنوان. ويبقى سجلّ الأسعار وأعداد النقرات، وهي بيانات عن المنتجات والمتاجر لا عنك.',
    'privacy.rights.export':
      'لا توجد بعد صفحة لتنزيل نسخة من بياناتك ولا لتغيير بريد الحساب. راسلنا وينفّذها شخص يدوياً.',
    'privacy.rights.accountLink': 'افتح صفحة حسابك لحذف حسابك',
    'privacy.rights.how':
      'لأي طلب من هذه، استعمل صفحة «اتصل بنا» أو العنوان المذكور في أعلى الصفحة.',

    'privacy.security.title': 'كيف نحمي حسابك',
    'privacy.security.password':
      'كلمة المرور لا تُحفظ كما كتبتها، بل كبصمة مشفّرة بطيئة الحساب عمداً. ولا نرسل كلمة مرور في بريد أبداً: رابط إعادة التعيين ينتهي ويعمل مرة واحدة.',
    'privacy.security.cookie':
      'كوكي الجلسة لا يستطيع أي كود في الصفحة قراءته، ولا يُخزَّن رمز الدخول في متصفّحك.',
    'privacy.security.uploads':
      'كل صورة مرفوعة تُكتب من جديد قبل حفظها، فلا يمرّ ملف ضار متخفّياً في هيئة صورة.',
    'privacy.security.rate': 'نحدّ عدد محاولات الدخول وإنشاء الحساب من العنوان الواحد.',
    'privacy.security.https': 'نطلب من المتصفّح ألّا يتصل بالموقع إلا عبر اتصال مشفّر.',
    'privacy.security.honest':
      'لا نستطيع أن نعدك بأن شيئاً لن ينكسر أبداً. لكن إن وقع خرق يمسّ بياناتك، نُبلغ المتضرّرين والجهة المختصة.',

    'privacy.changes.title': 'إن تغيّرت هذه الصفحة',
    'privacy.changes.p1':
      'إن غيّرنا شيئاً غيّرنا معه تاريخ التحديث في الأعلى. وإن كان التغيير جوهرياً — كأن نبدأ بجمع شيء جديد — نقوله بوضوح على الموقع، لا في سطر مدفون هنا.',

    'privacy.contact.title': 'كيف تتواصل معنا',
    'privacy.contact.p1':
      'أي سؤال عن هذه الصفحة، أو أي طلب يخصّ بياناتك، أرسله من صفحة «اتصل بنا» أو إلى العنوان المذكور في الأعلى. نرد على البريد الذي تكتبه.',
    'privacy.contact.link': 'افتح صفحة «اتصل بنا»',

    // --- Terms of use
    // Written for two audiences at once: a shopper who needs to know the
    // price here is not a promise, and a shop owner about to be asked for an
    // account. The merchant section is the one that has to be exact, because
    // it is what someone agrees to when they upload a photo of a phone.
    'terms.title': 'شروط الاستخدام',
    'terms.blurb': 'ما الذي تقدّمه هذه الخدمة وما لا تقدّمه — للمتسوّقين وللمتاجر.',

    'terms.what.title': 'ما هذه الخدمة',
    'terms.what.p1':
      '«احسن سعر» يقارن أسعار أجهزة معروضة في متاجر أردنية، ويدلّك على أين تجدها بأقل سعر.',
    'terms.what.p2':
      'نحن لسنا متجراً. لا نبيع شيئاً، ولا يتم أي شراء ولا أي دفع على هذا الموقع. حين تقرّر الشراء تتعامل مع المتجر مباشرة: البيع والسعر والفاتورة والكفالة والاستبدال كلها بينك وبينه، ولسنا طرفاً فيها.',
    'terms.what.p3':
      'باستخدامك للموقع أنت توافق على ما في هذه الصفحة. وإن لم توافق، فلا تستخدمه.',

    'terms.prices.title': 'عن الأسعار المعروضة',
    'terms.prices.sources':
      'للأسعار هنا مصدران: أسعار نقرأها آلياً من صفحات المتاجر المنشورة للعموم، وأسعار يدخلها التاجر بنفسه.',
    'terms.prices.stale':
      'السعر هنا قد يكون قديماً أو خاطئاً. المتاجر تغيّر أسعارها في أي لحظة، وقد يخطئ التاجر في الإدخال، وقد نخطئ نحن في القراءة.',
    'terms.prices.governs':
      'السعر المعتمد هو سعر المتجر نفسه وقت الشراء. ما تراه عندنا دليل، لا وعد.',
    'terms.prices.age':
      'نعرض متى تحقّقنا آخر مرة من كل سعر، فانظر إلى هذا التاريخ قبل أن تبني عليه.',
    'terms.prices.matching':
      'نحاول أن نطابق عروض المتاجر على المنتج نفسه، ونبيّن درجة قرب المطابقة. المطابقة القريبة ليست بالضرورة المنتج ذاته: تأكّد من السعة واللون والحالة قبل الشراء.',
    'terms.prices.report':
      'إن وجدت سعراً خاطئاً فأخبرنا وسنصحّحه، لكننا لا نستطيع إلزام أي متجر ببيعك بسعر ظهر عندنا.',

    'terms.account.title': 'حسابك',
    'terms.account.email':
      'تحتاج بريداً إلكترونياً حقيقياً تصل إليه الرسائل، لأن التأكيد وإعادة تعيين كلمة المرور والتنبيهات كلها تصل عليه.',
    'terms.account.password':
      'كلمة المرور مسؤوليتك. لا تشاركها مع أحد، وما يجري من حسابك يُحسب عليك.',
    'terms.account.breach':
      'إن ظننت أن أحداً دخل إلى حسابك، غيّر كلمة المرور وراسلنا فوراً.',
    'terms.account.one':
      'حساب واحد لكل شخص أو متجر. لا تُنشئ حسابات إضافية لتجاوز حدّ أو إيقاف.',

    'terms.merchant.title': 'إن كنت تاجراً',
    'terms.merchant.intro': 'حين تنشر عرضاً على «احسن سعر» فأنت توافق على ما يلي:',
    'terms.merchant.accurate':
      'أن يكون العرض صحيحاً: جهاز تملكه فعلاً، بسعر تبيع به فعلاً، وأن تحدّثه إن تغيّر أو نفد.',
    'terms.merchant.condition':
      'أن تصف الحالة بصدق: جديد أو مستعمل أو مجدّد، ونسبة البطارية، وأي ضرر — حتى ما لا يظهر في الصورة.',
    'terms.merchant.public':
      'أن تعرف أن بيانات تواصلك — الهاتف وواتساب وحساباتك — تُنشر على صفحة المنتج لكل زائر، لا لمن يطلبها وحده.',
    'terms.merchant.freeText':
      'أن ما تكتبه بحرّية — اسم المتجر وملاحظات الضرر وملاحظات العرض — يُنشر كما هو. لا تكتب فيه ما لا تريد نشره.',
    'terms.merchant.photos':
      'أن تكون الصورة التي ترفعها لك: صوّرتها أنت أو تملك حق استخدامها، وهي للجهاز المعروض نفسه. لا ترفع صورة من موقع متجر آخر ولا من موقع الشركة المصنّعة إلا إن كان يحقّ لك ذلك.',
    'terms.merchant.licence':
      'أن تأذن لنا بعرض صور عروضك على الموقع ما دام العرض قائماً. الصورة تبقى ملكك، واحذفها متى شئت فتُحذف عندنا.',
    'terms.merchant.remove':
      'أنه يحقّ لك أن تطلب إزالة متجرك أو أي عرض فيه في أي وقت، وننفّذ ذلك.',
    'terms.merchant.review':
      'نراجع كل متجر قبل أن تظهر أسعاره للمتسوّقين. ويحقّ لنا إخفاء أو إزالة أي عرض مضلّل أو خاطئ أو مخالف للقانون، ونوضّح لك السبب.',
    'terms.merchant.taps':
      'نُظهر لك كم مرة ضغط أحدهم «اتصال» أو «واتساب» على عروضك. هذا عدد نقرات فقط: لا نعرف إن رنّ الهاتف، ولا إن تمّ بيع، ومن يضغط مرتين يُحسب مرتين. فلا تُقرأ هذه الأرقام على أنها زبائن أو مبيعات.',

    'terms.retailers.title': 'للمتاجر التي نقرأ أسعارها',
    'terms.retailers.p1':
      'نقرأ صفحات منشورة للعموم فقط، على مهل، ونعرّف عن أنفسنا في كل طلب، ونحترم ملف robots.txt.',
    'terms.retailers.p2':
      'هذا أدب تعامل، لا ادّعاء بأن أحداً أذن لنا. لا توجد بيننا وبين هذه المتاجر شراكة ولا اتفاق.',
    'terms.retailers.p3':
      'إن كنت تدير أحد هذه المتاجر ولا تريد أن تظهر أسعارك هنا، راسلنا ونزيلها.',

    'terms.use.title': 'ما لا يجوز على الموقع',
    'terms.use.harvest':
      'جمع أرقام التجّار أو بياناتهم من الموقع لاستعمالها في تسويق أو رسائل غير مطلوبة.',
    'terms.use.copy': 'نسخ محتوى الموقع آلياً أو إعادة نشره كخدمة مشابهة.',
    'terms.use.attack':
      'محاولة تعطيل الموقع، أو الدخول إلى حساب غيرك، أو الالتفاف على حدود الاستخدام.',
    'terms.use.illegal': 'نشر ما يخالف القانون، أو ما يخصّ شخصاً آخر بغير إذنه.',

    'terms.termination.title': 'إغلاق الحساب',
    'terms.termination.you':
      'تستطيع حذف حسابك بنفسك في أي وقت من صفحة حسابك. وحذف حساب تاجر يُخفي أسعاره عن الموقع.',
    'terms.termination.link': 'افتح صفحة حسابك',
    'terms.termination.us':
      'ويحقّ لنا إيقاف أو إغلاق حساب يخالف هذه الشروط، ونذكر السبب حيثما أمكن. وما يبقى بعد الحذف مشروح في صفحة الخصوصية.',
    'terms.termination.privacyLink': 'اقرأ سياسة الخصوصية',

    'terms.warranty.title': 'لا يوجد ضمان',
    'terms.warranty.p1':
      'الموقع يُقدَّم كما هو. لا نعد بأنه سيعمل دائماً، ولا بأن كل معلومة فيه صحيحة أو كاملة أو محدّثة.',
    'terms.warranty.p2':
      'ولسنا مسؤولين عن صفقة عقدتها مع متجر، ولا عن سعر دفعته، ولا عن جهاز اشتريته، ولا عن طريقة تعامل متجر معك. لا شيء في هذه الصفحة ولا في الموقع يُعدّ ضماناً من أي نوع.',
    'terms.warranty.p3':
      'وفي حدود ما يسمح به القانون، لا نتحمّل أي خسارة غير مباشرة نتجت عن استعمال الموقع.',

    'terms.changes.title': 'تعديل الشروط',
    'terms.changes.p1':
      'قد نعدّل هذه الشروط. تاريخ آخر تعديل مذكور في الأعلى، واستمرارك في استعمال الموقع بعده يعني قبولك به. وإن كان التعديل جوهرياً على التجّار، نخبرهم.',

    'terms.law.title': 'القانون والاختصاص',
    'terms.law.p1':
      'تخضع هذه الشروط لقانون الدولة المذكورة في أعلى هذه الصفحة، وتُنظر أي منازعة أمام محاكمها.',
    'terms.law.p2':
      'أما البيانات الشخصية فيحكمها قانون حماية البيانات الشخصية الأردني رقم 24 لسنة 2023.',

    'terms.contact.title': 'أسئلة',
    'terms.contact.p1':
      'أي سؤال عن هذه الشروط، أو طلب إزالة عرض أو متجر، أرسله من صفحة «اتصل بنا».',
    'terms.contact.link': 'افتح صفحة «اتصل بنا»',
  },

  en: {
    'brand.name': 'Ahsan Se3r',
    'brand.tagline': 'Compare prices in Jordan',
    'nav.wishlist': 'Wishlist',
    'nav.alerts': 'Alerts',
    'nav.myShop': 'My shop',
    'nav.admin': 'Admin',
    'nav.account': 'Account',
    'nav.login': 'Login',
    'nav.logout': 'Logout',
    'nav.toggleLanguage': 'العربية',
    'nav.toggleTheme': 'Dark mode',
    'nav.toggleThemeLight': 'Light mode',
    'nav.menu': 'Menu',
    'nav.closeMenu': 'Close menu',

    // The Arabic name stays in the English site title: it is the name on the
    // logo, and the one a shopper who switched language will still recognise.
    // No crawler reads this table -- see the note on the Arabic one.
    'meta.siteTitle': 'Ahsan Se3r | احسن سعر — Compare electronics prices in Jordan',
    'meta.pageTitle': '{page} — Ahsan Se3r',
    'meta.description':
      'Compare phone, laptop and monitor prices across shops in Jordan and find the exact product you want at the lowest price.',
    'meta.results.title': 'Prices for “{query}”',
    'meta.results.description':
      'Compare prices for “{query}” across shops in Jordan, from exact matches to close and similar products.',
    'meta.browse.description': '{category}: compare prices across shops in Jordan and find the lowest.',
    'meta.product.titleFrom': '{name} from {price}',
    'meta.product.description': 'Compare prices for {name} across shops in Jordan.',
    'meta.product.descriptionFrom': 'Compare prices for {name} across shops in Jordan. New from {price}.',
    'meta.verifyEmail.title': 'Confirm your email',

    'home.title': 'Compare prices in Jordan',
    'home.subtitle':
      'Include storage and colour to get an exact match.',
    'home.deals': 'Biggest savings right now',
    'home.dealsHint': 'The gap between the cheapest and dearest shop',
    'home.save': 'Save',
    'home.at': 'at',
    'home.upTo': 'up to',
    'home.elsewhere': 'elsewhere',
    'home.comparedAcross': 'compared across {count} shops',

    // --- Browsing the catalogue (home page, under the savings)
    'browse.title': 'Browse the shops',
    'browse.hint': 'Real prices from Jordanian shops',
    'browse.count': '{count} products',
    'category.phones': 'Phones',
    'category.laptops': 'Laptops',
    'category.monitors': 'Monitors',
    'browse.showMore': 'Show more',
    'browse.showingOf': 'Showing {shown} of {total}',
    'browse.empty': 'Nothing in this category yet.',
    'browse.loadError': 'Could not load the products.',
    'browse.moreColours': 'in {count} more colours',
    'browse.moreColoursOne': 'in one more colour',

    'search.placeholder': 'Search — try including storage and colour',
    'search.button': 'Search',
    'search.try': 'Try:',
    'search.results': '{count} products',
    'search.resultsOne': '1 product',
    'search.showingFor': 'Showing results for “{corrected}”',
    'search.searchInstead': 'Search instead for “{original}”',
    'search.suggestions': 'Suggestions',
    'search.resultsFor': 'Results for “{query}”',
    'common.page': 'Page {page}',
    'search.counts': '({exact} exact · {close} close · {similar} similar)',
    'search.sortLabel': 'Sort within each group',
    'search.sort.priceAsc': 'Cheapest first',
    'search.sort.priceDesc': 'Most expensive first',
    'search.sort.name': 'Name (A–Z)',
    'search.empty': 'Nothing matched that search.',
    'search.emptyHint':
      'Try the product name with its storage, like “iPhone 15 128GB”.',
    'search.understood': 'We read your search as',
    'search.loadError': 'Could not load results.',
    'search.byName':
      'Searching by name. Add details like storage or colour — for example “iPhone 15 128GB Black” — to get exact matches.',
    'search.lookingFor': 'Looking for:',
    'search.ofTotal': '{shown} of {total}',
    'auth.linkSent': 'Link sent — check your inbox.',
    'auth.sending': 'Sending…',

    'tier.exact': 'Exact match',
    'tier.exact.blurb': 'Everything you asked for',
    'tier.close': 'Close matches',
    'tier.close.blurb': 'Same product, one detail differs',
    'tier.similar': 'Similar products',
    'tier.similar.blurb': 'Related, but not what you searched for',
    'tier.matchPercent': '{score}% match',
    'tier.nameMatch': 'Name match',
    'tier.nameMatchTitle': 'Found by name or brand — we could not rank this one on its specifications.',
    'tier.scoreTitle': 'Match score: {score}%',

    // --- Why a match is not exact. One key per attribute; see the Arabic
    // table for why this is not a single template.
    'match.diff.brand.different': 'different brand ({found}, not {wanted})',
    'match.diff.brand.missing': 'brand not listed',
    'match.diff.model.different': 'different model ({found}, not {wanted})',
    'match.diff.model.missing': 'model not listed',
    'match.diff.variant.different': 'different variant ({found}, not {wanted})',
    'match.diff.variant.missing': 'variant not listed',
    'match.diff.storage.different': 'different storage ({found}, not {wanted})',
    'match.diff.storage.missing': 'storage not listed',
    'match.diff.ram.different': 'different memory ({found}, not {wanted})',
    'match.diff.ram.missing': 'memory not listed',
    'match.diff.color.different': 'different colour ({found}, not {wanted})',
    'match.diff.color.missing': 'colour not listed',
    'match.diff.cpu.different': 'different processor ({found}, not {wanted})',
    'match.diff.cpu.missing': 'processor not listed',
    'match.diff.size.different': 'different screen size ({found}, not {wanted})',
    'match.diff.size.missing': 'screen size not listed',
    'match.diff.resolution.different': 'different resolution ({found}, not {wanted})',
    'match.diff.resolution.missing': 'resolution not listed',
    'match.diff.refresh.different': 'different refresh rate ({found}, not {wanted})',
    'match.diff.refresh.missing': 'refresh rate not listed',
    'match.diff.panel.different': 'different panel type ({found}, not {wanted})',
    'match.diff.panel.missing': 'panel type not listed',
    'match.diff.different': 'different {label} ({found}, not {wanted})',
    'match.diff.missing': '{label} not listed',

    // --- Attribute names on their own, for the "we searched for" chips.
    'match.attr.brand': 'brand',
    'match.attr.model': 'model',
    'match.attr.variant': 'variant',
    'match.attr.storage': 'storage',
    'match.attr.ram': 'memory',
    'match.attr.color': 'colour',
    'match.attr.cpu': 'processor',
    'match.attr.size': 'screen size',
    'match.attr.resolution': 'resolution',
    'match.attr.refresh': 'refresh rate',
    'match.attr.panel': 'panel type',

    // --- Product photos
    'photo.label': 'Product photo',
    'photo.hint': 'A clear shot of the actual unit. JPG, PNG or WebP, up to {mb}MB.',
    'photo.add': 'Add photo',
    'photo.change': 'Change photo',
    'photo.remove': 'Remove photo',
    'photo.uploadError': 'Could not upload the photo. Try again.',
    'photo.errorType': 'Choose a JPG, PNG or WebP image.',
    'photo.errorSize': 'The image is larger than {mb}MB.',
    'photo.error.empty': 'The file is empty.',
    'photo.error.too_large': 'The file is too large.',
    'photo.error.svg': 'SVG files are not accepted. Upload a photograph.',
    'photo.error.not_an_image': 'That file is not an image we can read.',
    'photo.error.unsupported_format': 'Use a JPG, PNG or WebP photo.',
    'photo.error.too_many_pixels': "The image's resolution is too high.",
    'product.noPhoto': 'No photo',
    'common.networkError': 'Cannot reach the server.',

    // --- Attribute values. English is the canonical form the engine already
    // speaks, so these exist to give the Arabic table something to be checked
    // against -- key parity is what stops a colour being translated on one
    // side only.
    'match.value.black': 'black',
    'match.value.white': 'white',
    'match.value.silver': 'silver',
    'match.value.gold': 'gold',
    'match.value.blue': 'blue',
    'match.value.red': 'red',
    'match.value.green': 'green',
    'match.value.purple': 'purple',
    'match.value.pink': 'pink',
    'match.value.yellow': 'yellow',
    'match.value.orange': 'orange',
    'match.value.gray': 'gray',
    'match.value.cream': 'cream',
    'match.value.mint': 'mint',
    'match.value.beige': 'beige',
    'match.value.graphite': 'graphite',
    'match.value.titanium': 'titanium',
    'match.value.starlight': 'starlight',
    'match.value.lavender': 'lavender',
    'match.value.midnight': 'midnight',
    'match.value.rose_gold': 'rose gold',
    'match.value.space_gray': 'space gray',
    'match.value.sierra_blue': 'sierra blue',
    'match.value.pacific_blue': 'pacific blue',
    'match.value.sky_blue': 'sky blue',
    'match.value.midnight_green': 'midnight green',
    'match.value.alpine_green': 'alpine green',
    'match.value.deep_purple': 'deep purple',
    'match.value.natural_titanium': 'natural titanium',
    'match.value.blue_titanium': 'blue titanium',
    'match.value.phantom_black': 'phantom black',
    'match.value.base': 'base',
    'match.value.pro': 'Pro',
    'match.value.pro_max': 'Pro Max',
    'match.value.plus': 'Plus',
    'match.value.pro_plus': 'Pro+',
    'match.value.ultra': 'Ultra',
    'match.value.mini': 'Mini',
    'match.value.max': 'Max',
    'match.value.air': 'Air',
    'match.value.fe': 'FE',

    'product.back': 'Back to search',
    'product.new': 'New',
    'product.newFrom': 'New — from {price}',
    'product.used': 'Used & refurbished',
    'product.usedFrom': 'Used & refurbished — from {price}',
    'product.usedHint':
      'Sold by local shops. Check the battery health and condition notes before you call.',
    'product.noNewListings': 'No shop is currently listing this new.',
    'product.noListings': 'No stores are currently listing this product.',
    'product.history': 'Price history',
    'product.notFound': 'That product no longer exists.',
    'product.loadError': 'Could not load this product.',

    'table.store': 'Store',
    'table.price': 'Price',
    'table.delivery': 'Delivery',
    'table.total': 'Total',
    'table.warranty': 'Warranty',
    'table.availability': 'Availability',
    'table.buy': 'Buy',
    'table.bestDeal': 'Best deal',
    'table.localShop': 'Local shop',
    'table.inStock': 'In stock',
    'table.outOfStock': 'Out of stock',
    'table.free': 'Free',
    'table.visit': 'Visit',
    'table.months': '{count} months',
    'table.updated': 'Updated {age}',
    'table.stalePrice': 'Price confirmed {age} — check before buying',
    'table.battery': 'Battery {percent}%',
    'table.hasDamage': 'Has damage',
    'table.noDamage': 'No damage reported',

    'time.today': 'today',
    'time.yesterday': 'yesterday',
    'time.daysAgo': '{count} days ago',
    'time.monthAgo': 'a month ago',
    'time.monthsAgo': '{count} months ago',

    'auth.login': 'Login',
    'auth.register': 'Register',
    'auth.email': 'Email',
    'auth.password': 'Password',
    'auth.confirmPassword': 'Confirm password',
    'auth.whatBringsYou': 'What brings you here?',
    'auth.iAmShopping': 'I am shopping',
    'auth.iAmShoppingBlurb': 'Compare prices, save products, get price alerts',
    'auth.iHaveShop': 'I have a shop',
    'auth.iHaveShopBlurb': 'List your prices so shoppers can find and call you',
    'auth.noAccount': 'No account?',
    'auth.haveAccount': 'Already have an account?',
    'auth.verifyBanner': 'Confirm your email to receive price alerts.',
    'auth.resendLink': 'Resend the link',

    // --- Signing in with Google or Apple. The failure keys carry the API's
    // own error codes; see the Arabic table for why.
    'auth.continueWithGoogle': 'Continue with Google',
    'auth.continueWithApple': 'Sign in with Apple',
    'auth.or': 'or',
    'auth.oauth.signingIn': 'Finishing your sign-in…',
    'auth.oauth.problemTitle': 'We could not finish signing you in',
    'auth.oauth.cancelledTitle': 'Sign-in not completed',
    'auth.oauth.state_invalid':
      'That sign-in attempt expired or was already used. Start again.',
    'auth.oauth.unavailable':
      'Signing in with Google or Apple is unavailable right now. You can sign in with your email and password instead.',
    'auth.oauth.provider_error':
      'The provider did not complete the sign-in. If you cancelled, that is all that happened — try again, or sign in with your email and password.',
    'auth.oauth.email_unverified':
      'Google or Apple would not confirm that this email address is yours. Verify the address in your account settings there and try again, or sign in here with an email and password instead.',
    'auth.oauth.unknown':
      'The sign-in did not complete. Try again, or sign in with your email and password.',

    // --- The account page. The consequences of a deletion are listed one by
    // one rather than summarised; see the Arabic table for why.
    'account.title': 'Your account',
    'account.blurb': 'Your details, and how to delete the account if you want to.',
    'account.emailStatus': 'Email status',
    'account.verified': 'Confirmed',
    'account.unverified': 'Not confirmed',
    'account.unverifiedHint':
      'Price alerts are only sent to a confirmed address. Use the banner at the top of the page to send yourself a new link.',
    'account.role': 'Account type',
    'account.role.buyer': 'Shopper',
    'account.role.merchant': 'Merchant',
    'account.role.admin': 'Administrator',
    'account.created': 'Opened',
    'account.limits':
      'There is not yet a page to change the address on an account, or to download a copy of your data. Write to us and a person will do it by hand.',
    'account.limitsLink': 'Write to us',
    'account.delete.title': 'Delete your account',
    'account.delete.blurb':
      'Deleting is final: there is no undo, nothing kept aside, and no way for us to bring an account back afterwards.',
    'account.delete.start': 'Delete my account',
    'account.delete.whatTitle': 'What deleting actually does',
    'account.delete.goneTitle': 'Gone immediately, and for good',
    'account.delete.gone.account':
      'Your account and your email address. The address is free to register again straight away.',
    'account.delete.gone.saved': 'Everything you saved: your wishlist and every price alert.',
    'account.delete.gone.sessions':
      'Every sign-in session on every device, this one included.',
    'account.delete.gone.social': 'Any Google or Apple sign-in linked to the account.',
    'account.delete.keptTitle': 'Kept, with what named you removed',
    'account.delete.kept.support':
      'Support messages you sent keep their text, so we still have the history of the conversation, but the reply-to address is scrubbed and the message no longer names you.',
    'account.delete.untouchedTitle': 'Untouched',
    'account.delete.untouched.taps':
      'The tap counters that tell a shop how many shoppers asked for its number. They are anonymous by design and refer to no person.',
    'account.delete.merchantTitle': 'If you own a shop',
    'account.delete.merchant.retired':
      'Your shop is not deleted with the account, it is retired: taken off the site at once, its phone, WhatsApp and social links erased, and its name changed — shop names are unique, and a retired shop holding on to yours would reserve it forever and block that business from ever registering again.',
    'account.delete.merchant.photos':
      'Every product photo you uploaded is deleted. It is your own work, it may show you or your premises, and it can never be displayed again.',
    'account.delete.merchant.listings':
      'Your listings, their prices and the price history stay. They belong to the catalogue shoppers are comparing, not to your account.',
    'account.delete.merchantLink': 'Look at your shop first',
    'account.delete.confirmTitle': 'Type your email address to confirm',
    'account.delete.confirmWhy':
      'Your address, not your password: an account created through Google has no password at all, and this has to work for those accounts too. Capitals and stray spaces do not matter.',
    'account.delete.confirmLabel': 'Your email address',
    'account.delete.confirm': 'Delete my account permanently',
    'account.delete.deleting': 'Deleting…',
    'account.delete.mismatch': 'That is not the email address on this account.',
    'account.delete.error': 'We could not delete the account. Try again.',
    'account.deleted.title': 'Your account has been deleted.',
    'account.deleted.blurb':
      'Everything listed on the account page is gone. Your email address is free to use again if you ever want to come back.',

    'merchant.listYourShop': 'List your shop',
    'merchant.listYourShopBlurb':
      'Add your prices and shoppers comparing phones in Jordan will see them, with your phone number to call. Free, and you do not need a website.',
    'merchant.shopName': 'Shop name',
    'merchant.shopNameHint':
      'This is what shoppers see. It cannot be changed later, so use the name your customers know.',
    'merchant.phone': 'Phone',
    'merchant.whatsapp': 'WhatsApp',
    'merchant.facebook': 'Facebook page',
    'merchant.instagram': 'Instagram',
    'merchant.optional': '(optional)',
    'merchant.registerShop': 'Register shop',
    'merchant.registering': 'Registering…',
    'merchant.reviewNote':
      'We check every shop before its prices go live, so it may be a day before yours appears in search.',
    'merchant.verified': 'Verified — your prices are live',
    'merchant.pending': 'Awaiting review — your prices are not public yet',
    'merchant.pendingNote':
      'You can add your products now. They will appear in search as soon as we have confirmed your shop.',
    'merchant.contactHeading': 'How shoppers reach you',
    'merchant.saveContact': 'Save contact details',
    'merchant.saved': 'Saved',
    'merchant.addProduct': 'Add a product',
    'merchant.productName': 'Product name',
    'merchant.priceJod': 'Price (JOD)',
    'merchant.add': 'Add',
    'merchant.saving': 'Saving…',
    'merchant.condition': 'Condition',
    'merchant.conditionNew': 'New / sealed',
    'merchant.conditionUsed': 'Used',
    'merchant.conditionRefurbished': 'Refurbished',
    'merchant.usedNote':
      'Buyers ask these before anything else. Listings without them are rejected.',
    'merchant.batteryHealth': 'Battery health %',
    'merchant.warrantyMonths': 'Warranty (months)',
    'merchant.anyDamage': 'Any damage?',
    'merchant.noDamage': 'No damage',
    'merchant.yesDamage': 'Yes — I will describe it',
    'merchant.describeDamage': 'Describe the damage',
    'merchant.anythingElse': 'Anything else?',
    'merchant.nameHint':
      'Write the product the way you would say it to a customer, including storage and colour. Adding a product you already list in the same condition updates its price.',
    'merchant.yourProducts': 'Your products',
    'merchant.noProducts': 'Nothing listed yet. Add your first product above.',
    'merchant.notSearchable':
      'Not shown in search — we could not tell what this product is. Try including the brand, model and storage.',
    'merchant.matchedTo': 'Matched to “{name}”',
    'merchant.notUpdatedSince': 'Not updated since {age} — shoppers see a warning',
    'merchant.remove': 'Remove',
    'merchant.confirmRemove':
      'Remove “{name}” from your shop? This cannot be undone.',
    'merchant.save': 'Save',
    'merchant.productCount': '{count} products',
    'merchant.productCountOne': '1 product',
    // --- Contact taps -------------------------------------------------
    'stats.heading': 'How shoppers reached you',
    'stats.window': 'last {days} days',
    'stats.taps': '{count} taps',
    'stats.tapsOne': '1 tap',
    'stats.tapsNone': 'No taps yet',
    'stats.call': 'Call',
    'stats.whatsapp': 'WhatsApp',
    'stats.facebook': 'Facebook',
    'stats.instagram': 'Instagram',
    'stats.topProducts': 'Most asked about',
    'stats.explainer':
      'These are taps on Call or WhatsApp — a shopper asking for your number. We cannot see whether the call was made or anything was sold.',
    'stats.unverifiedHint': 'Your shop is not verified yet, so your prices are hidden from shoppers and no taps will arrive.',
    'merchant.loadError': 'Could not load your shop.',

    // --- Added when the admin screen and the last English-only
    // surfaces were translated. The handoff had claimed for a while
    // that admin was the ONLY untranslated screen; it was not.
    'admin.title': 'Admin',
    'admin.platform': 'Platform',
    'admin.merchantStores': 'Merchant stores',
    'admin.merchantStoresBlurb': "A merchant's prices stay out of search until the claim is confirmed. Check that the account really belongs to the shop before approving — anyone can register under any name.",
    'admin.priceAnomalies': 'Price anomalies',
    'admin.users': 'Users ({count})',
    'admin.loading': 'Loading...',
    'admin.shop': 'Shop',
    'admin.account': 'Account',
    'admin.contact': 'Contact',
    'admin.listings': 'Listings',
    'admin.status': 'Status',
    'admin.taps': 'Taps (30d)',
    'admin.role': 'Role',
    'admin.email': 'Email',
    'admin.id': 'ID',
    'admin.product': 'Product',
    'admin.was': 'Was',
    'admin.now': 'Now',
    'admin.verified': 'Verified',
    'admin.pending': 'Pending',
    'admin.declined': 'Declined',
    'admin.emailUnconfirmed': 'email unconfirmed',
    'admin.approve': 'Approve',
    'admin.approveAnyway': 'Approve anyway',
    'admin.withdraw': 'Withdraw',
    'admin.decline': 'Decline',
    'admin.delete': 'Delete',
    'admin.remove': 'Remove',
    'admin.save': 'Save',
    'admin.change': 'Change',
    'admin.noShops': 'No shops have registered yet.',
    'admin.shopHasNothing': 'This shop has not listed anything yet.',
    'admin.noAnomalies': 'No price moved more than 50% in the last 24 hours.',
    'admin.showListings': 'Show what this shop lists',
    'admin.emailUnconfirmedHint': 'This account has not confirmed its email address',
    'admin.tapsHint': 'Shoppers who tapped Call, WhatsApp or Facebook. Not calls made, and not sales.',
    'admin.stat.users': 'Users',
    'admin.stat.products': 'Products',
    'admin.stat.stores': 'Stores',
    'admin.stat.aliases': 'Store listings',
    'admin.stat.prices': 'Current prices',
    'admin.stat.history': 'History records',
    'admin.error.dashboard': 'Could not load the dashboard.',
    'admin.error.user': 'Could not delete that user.',
    'admin.error.store': 'Could not update that store.',
    'admin.error.decline': 'Could not decline that store.',
    'admin.error.shopListings': 'Could not load the products for that shop.',
    'admin.error.listing': 'Could not update that listing.',
    'admin.error.removeListing': 'Could not remove that listing.',
    'support.heading': 'Contact messages',
    'support.unread': '{count} unread',
    'support.showHandled': 'Show handled',
    'support.nothingWaiting': 'Nothing waiting.',
    'support.markHandled': 'Mark handled',
    'support.reopen': 'Reopen',
    'support.noSubject': 'No subject',
    'support.account': '(account: {email})',
    'support.loadError': 'Could not load the messages.',
    'support.updateError': 'Could not update that message.',
    'verify.confirmed': 'Email confirmed',
    'verify.confirmedBlurb': 'Your address is verified. Price alerts will now reach you.',
    'verify.linkFailed': 'This link did not work',
    'verify.linkFailedBlurb': 'It may have expired or already been used. Links work once and last 24 hours.',
    'verify.signInAndResend': 'Sign in and use “Resend the link” to get a new one.',
    'alerts.title': 'Price alerts',
    'alerts.none': 'No alerts yet.',
    'alerts.noneBlurb': 'Open a product and set a target price to be told when it drops.',
    'alerts.targetReached': 'Target reached — buy now',
    'alerts.delete': 'Delete',
    'actions.alertSet': 'Alert set',
    'actions.viewWishlist': 'View wishlist',
    'actions.viewAlerts': 'View alerts',
    'actions.tellMeBelow': 'Tell me when it drops below',
    'auth.adminOnly': 'Admin only',
    'auth.noAccess': 'Your account does not have access to this page.',
    'common.startSearching': 'Start searching',
    'common.clickToChange': 'Click to change',
    'common.facebookPage': 'Facebook page',
    'common.priceFromShop': 'Price submitted by the shop',
    'common.priceHistoryByStore': 'Price history by store',
    'merchant.damageExample': 'Hairline crack, bottom right of the screen',
    'merchant.notesExample': 'Original box and charger included',

    'merchant.saveError': 'Could not save the product.',

    'common.loading': 'Loading…',
    'common.error': 'Something went wrong',
    'common.notFound': 'Page not found',
    'common.backHome': 'Back to search',
    'common.stores': '{count} stores',
    'common.storeOne': '1 store',
    'common.notInStock': 'Not in stock',
    'common.orUsedFrom': 'or used from {price}',
    'common.usedOnly': 'used only',
    'common.inclDelivery': 'incl. delivery',
    'common.currency': 'JOD',
    'actions.save': 'Save',
    'actions.saved': 'Saved to wishlist',
    'actions.saving': 'Saving…',
    'actions.setAlert': 'Set price alert',
    'actions.cancel': 'Cancel',
    'actions.createAlert': 'Create alert',
    'actions.settingAlert': 'Setting…',
    'actions.saveError': 'Could not save this product.',
    'actions.alertError': 'Could not create that alert.',
    'actions.loginPrompt': 'Log in to save this product or set a price alert.',
    'chart.noHistory':
      'No price changes recorded yet. History builds up as stores change their prices between scrapes.',
    'auth.forgotPassword': 'Forgot your password?',
    'auth.loggingIn': 'Logging in…',
    'auth.invalidCredentials': 'Invalid email or password.',
    'auth.forgotTitle': 'Reset your password',
    'auth.forgotBlurb':
      'Enter your email and we will send you a link to choose a new password.',
    'auth.sendResetLink': 'Send the link',
    'auth.resetSent':
      'If an account exists for that address, we have sent it a link. Check your inbox.',
    'auth.resetTitle': 'Choose a new password',
    'auth.newPassword': 'New password',
    'auth.setPassword': 'Save password',
    'auth.resetDone': 'Your password has been changed. You can sign in now.',
    'auth.resetInvalid': 'This link is invalid or has expired. Request a new one.',
    'auth.backToLogin': 'Back to login',
    'auth.passwordsDoNotMatch': 'The passwords do not match.',
    'nav.contact': 'Contact us',
    'support.title': 'Contact us',
    'support.blurb':
      'Hit a problem, or have a question? Write to us and we will reply by email.',
    'support.yourEmail': 'Your email',
    'support.emailHint': 'We will reply to this address.',
    'support.subject': 'Subject',
    'support.message': 'Describe the problem',
    'support.send': 'Send',
    'support.sending': 'Sending…',
    'support.sent': 'We have your message. We will get back to you shortly.',
    'support.error': 'Could not send the message. Please try again.',
    'wishlist.title': 'Wishlist',
    'wishlist.empty': 'Nothing saved yet.',
    'wishlist.emptyHint': 'Search for a product and press Save to track its price.',
    'wishlist.remove': 'Remove',
    'wishlist.loadError': 'Could not load your wishlist.',
    'wishlist.from': 'from',
    'common.previous': 'Previous',
    'common.next': 'Next',

    // --- Footer
    'footer.nav': 'Site links',
    'footer.notAShop':
      'We only compare prices. We sell nothing, and no purchase or payment happens on this site.',
    'footer.about': 'About',
    'footer.lab': 'How matching works',
    'footer.privacy': 'Privacy',
    'footer.terms': 'Terms',
    'footer.copyright': '© {year} Ahsan Se3r',

    // --- About (pages/About.jsx). See the note on the Arabic table.
    'about.metaTitle': 'About us',
    'about.title': 'About Ahsan Se3r',
    'about.lead':
      'Ahsan Se3r (احسن سعر) is a free Jordanian website that compares the prices of phones, laptops and monitors across shops in Jordan.',
    'about.how.title': 'How it works',
    'about.how.sources':
      "We read prices from online shops in Jordan several times a day, and shops without a website add their own. No shop's prices appear until we have confirmed it is a real shop.",
    'about.how.matching':
      'Type the product exactly as you want it, such as “iPhone 15 128GB Black”. Exact matches come first, then close and similar products, each labelled with how it differs from what you asked for.',
    'about.how.used':
      'Used devices are listed separately and are never compared as a cheaper version of a new one.',
    'about.buying.title': 'We sell nothing',
    'about.buying.p1':
      'No purchase or payment happens on this site. When you find the right price, you buy directly from the shop: on its website, or by calling it or messaging it on WhatsApp.',
    'about.buying.p2': 'You do not need an account to search and compare.',
    'about.shops.title': 'Do you have a shop?',
    'about.shops.p1':
      'If you run a shop in Jordan that sells these devices, you can create a shop account and add your prices, so customers reach you directly by phone or on WhatsApp.',
    'about.shops.link': 'Create a shop account',
    'about.how.lab': 'Try it yourself in the Matching Lab',
    'about.contact': 'A question or a correction? Write to us.',

    // --- The Matching Lab (pages/Lab.jsx)
    'lab.metaTitle': 'Matching Lab',
    'lab.title': 'Matching Lab',
    'lab.lead':
      'Type a search and the names stores give their products. See how this site reads each one — and how string similarity, the usual way to compare names, would rank them instead.',
    'lab.examples': 'Examples',
    'lab.example.storage': 'One character, another phone',
    'lab.example.arabic': 'Searching in Arabic',
    'lab.example.case': 'A case names its phone',
    'lab.example.plus': 'Pro+ is not Pro',
    'lab.example.samsung': 'A typo, two spellings',
    'lab.example.laptop': 'Laptops',
    'lab.example.monitor': 'Monitors',
    'lab.exampleNote.storage':
      'The example this site was built on: 128GB and 256GB are one character apart and are different phones, while word order is a large edit that changes nothing.',
    'lab.exampleNote.arabic':
      'Arabic spellings and digits are folded into the words the engine reads, and Apple’s “Midnight” is its black.',
    'lab.exampleNote.case':
      'A case repeats its phone’s name word for word. The store’s own category is what says it is a case.',
    'lab.exampleNote.plus':
      'Stores write the same phone with and without its brand, and one “+” separates two models.',
    'lab.exampleNote.samsung':
      'A misspelt brand is corrected — and the correction is shown. “Samsung S24” and “Galaxy S24” are the same phone.',
    'lab.exampleNote.laptop':
      'Categories are data: a laptop is scored on processor, storage and memory, with weights of its own.',
    'lab.exampleNote.monitor':
      'A monitor’s size and refresh rate outweigh the words it shares with the search. Brand is a gate.',
    'lab.exampleNote.custom': 'Your own example. Press Explain to see how it reads.',
    'lab.form.query': 'Search',
    'lab.form.listings': 'Listings, as stores name them',
    'lab.form.categoryHint':
      'The store category is optional — “Mobile” or “Mobile Case”, say — and is read exactly as the site reads it.',
    'lab.form.title': 'Listing {letter}',
    'lab.form.category': 'Store category',
    'lab.form.categoryLabel': 'Store category for listing {letter}',
    'lab.form.remove': 'Remove listing {letter}',
    'lab.form.add': 'Add a listing',
    'lab.form.full': 'Up to {max} listings',
    'lab.form.submit': 'Explain',
    'lab.form.dirty': 'Edited — press Explain to update.',
    'lab.form.tooShort': 'Type at least {min} characters to search.',
    'lab.form.noListings': 'Add at least one listing.',
    'lab.loading': 'Reading…',
    'lab.error': 'Could not explain this search. Try again in a moment.',
    'lab.reading.title': 'How the search was read',
    'lab.reading.stage.typed': 'You typed',
    'lab.reading.stage.spelling': 'Spelling corrected',
    'lab.reading.stage.arabic': 'Arabic, in the engine’s words',
    'lab.reading.stage.normalized': 'Cleaned up',
    'lab.reading.correction': 'Read “{typed}” as “{corrected}”.',
    'lab.reading.understood': 'Understood as',
    'lab.reading.unread':
      'This search names nothing the engine can read, so the site falls back to searching names and there is nothing to score.',
    'lab.rank.title': 'Two ways to rank the same listings',
    'lab.rank.similarity': 'String similarity',
    'lab.rank.similarityHint': 'How many characters the names share',
    'lab.rank.engine': 'This site',
    'lab.rank.engineHint': 'Which attributes agree',
    'lab.rank.headline':
      'String similarity ranks {worseLetter} “{worse}” above {betterLetter} “{better}”, {worseSimilarity} to {betterSimilarity}. This site scores them {worseScore} and {betterScore}: {reason}.',
    'lab.rank.headlineTie':
      'String similarity cannot tell {worseLetter} “{worse}” from {betterLetter} “{better}”: both score {betterSimilarity}. This site scores them {worseScore} and {betterScore}: {reason}.',
    'lab.rank.headlineUnscored':
      'String similarity ranks {worseLetter} “{worse}” above {betterLetter} “{better}”, {worseSimilarity} to {betterSimilarity}. This site gives {betterLetter} {betterScore} and does not score {worseLetter} at all: {reason}.',
    'lab.rank.headlineTieUnscored':
      'String similarity cannot tell {worseLetter} “{worse}” from {betterLetter} “{better}”: both score {betterSimilarity}. This site gives {betterLetter} {betterScore} and does not score {worseLetter} at all: {reason}.',
    'lab.rank.agree': 'Here the two methods agree on the order. Only one of them can say why.',
    'lab.rank.pairs':
      '{against} of {total} pairs in the opposite order, or tied where this site sees a difference.',
    'lab.short.gated': 'other brand',
    'lab.short.other_category': 'other kind',
    'lab.short.nothing_to_score': 'unscored',
    'lab.short.refused_by_store': 'turned away',
    'lab.short.unrecognised': 'unreadable',
    'lab.short.query_unread': 'unscored',
    'lab.reason.refused_by_store': 'the store files it under “{category}”, which this site does not carry',
    'lab.reason.other_category': 'it is a different kind of product',
    'lab.reason.nothing_to_score': 'the search names only a brand',
    'lab.reason.unrecognised': 'it is not a phone, laptop or monitor the engine can read',
    'lab.reason.query_unread': 'the search names nothing the engine can read',
    'lab.outcome.gated': 'Brand is a gate: {reason}. Excluded, however much else agrees.',
    'lab.outcome.refused_by_store':
      'The store files this under “{category}”. The last word of a store’s label says what the thing is, and this is not a phone, laptop or monitor — so it never enters the catalogue, whatever its title says.',
    'lab.outcome.other_category':
      'Read as {found}, and the search is for {wanted}. Different kinds of product are never compared.',
    'lab.outcome.nothing_to_score':
      'The search names only a brand, so there is nothing to score. On the site, listings like this appear unranked, as name matches.',
    'lab.outcome.unrecognised':
      'Not recognised as a phone, laptop or monitor, so it would never enter the catalogue.',
    'lab.outcome.query_unread': 'The search names nothing the engine can read, so this is not scored.',
    'lab.listSeparator': '; ',
    'lab.tier.exact': 'Exact',
    'lab.tier.close': 'Close',
    'lab.tier.similar': 'Similar',
    'lab.tier.excluded': 'Not shown',
    'lab.cards.title': 'Score by score',
    'lab.weights.lead':
      '{category}: every listing starts at 100 and loses the weight of each attribute the search asked for and did not get. An attribute the search did not mention costs nothing.',
    'lab.weights.barLabel': 'Attribute weights, adding up to 100',
    'lab.weights.gate':
      'Not scored, because it is a gate: {attributes}. If it differs, the listing is excluded however much else agrees.',
    'lab.legend.kept': 'Matched — points kept',
    'lab.legend.lost': 'Differs — weight lost',
    'lab.legend.unasked': 'Not in the search — costs nothing',
    'lab.ladder':
      'Tiers: 100 exact · 85 and up close · 70 and up similar · below 70 not shown in search.',
    'lab.bar.label': 'Score {score} out of 100',
    'lab.bar.keptTitle': '{name}: {value} — {weight} points kept',
    'lab.bar.lostTitle': '{name}: {found}, not {wanted} — {weight} points lost',
    'lab.bar.unaskedTitle': '{name}: not in the search, costs nothing',
    'lab.bar.notStated': 'not stated',
    'lab.card.storeCategory': 'Store category:',
    'lab.card.read': 'Read as',
    'lab.card.allKept': 'Everything the search asked for is here.',
    'lab.card.unasked': 'Not in the search, so free: {attributes}',
    'lab.card.ranks':
      'String similarity {similarity}, ranked {similarityRank} of {total} there and {engineRank} here.',
    'lab.honest':
      'Nothing on this page is a simulation. Your text goes to the same code the search runs, and nothing is saved.',
    'lab.similarityExplained':
      'String similarity is given the same cleaned-up text the engine reads — lowercase, punctuation removed, Arabic folded — so the only difference between the two columns is how they rank.',
    'lab.aboutLink': 'About Ahsan Se3r',

    // --- Legal pages: the furniture both of them share. The two blanks get a
    // panel of their own rather than a marker inside a sentence; see the
    // Arabic table for why.
    'legal.updated': 'Last updated: September 2026',
    'legal.contents': 'On this page',
    'legal.todo.title': 'This page is not finished',
    'legal.todo.blurb': 'Whoever operates this site must fill these in before publishing:',
    'legal.todo.blank': '⟨ to fill in ⟩',
    'legal.field.entity': 'Legal name of the entity that operates this site',
    'legal.field.dataContact':
      'Email address for data requests: access, correction, deletion',
    'legal.field.law': 'The country whose law governs these terms',

    // The operator's own details. The email is the address the policy promises
    // will answer a data request, so it has to be one that is actually read.
    'legal.value.entity': "Salem Ass'ad Mahmoud Mustafa",
    'legal.value.dataContact': 'altamarysalem@gmail.com',
    'legal.value.law': 'Jordan',

    // --- Privacy policy. Every sentence is a claim about what this code
    // does; see the Arabic table for the ones that were cut.
    'privacy.title': 'Privacy policy',
    'privacy.blurb': 'What we keep about you, why, and who else sees it.',

    'privacy.who.title': 'Who runs this site',
    'privacy.who.p1':
      'Ahsan Se3r compares the price of devices across Jordanian shops. The operator is named at the top of this page and is responsible for everything on it.',
    'privacy.who.p2':
      'We handle your data under Jordan’s Personal Data Protection Law No. 24 of 2023.',
    'privacy.who.p3':
      'This page is written as plainly as we could manage. If anything here is unclear, write to us and we will explain it.',

    'privacy.collect.title': 'What we collect',
    'privacy.collect.intro': 'Only what the service actually needs:',
    'privacy.collect.account':
      'Your account: your email address, your password stored as a one-way hash that cannot be turned back into the password, the kind of account, when it was created, and whether you have confirmed your address.',
    'privacy.collect.noProfile':
      'We do not ask for your name, your phone number, your address or your date of birth. There is no way to pay on this site, so we hold no card details.',
    'privacy.collect.shop':
      'If you have a shop: its name, website and logo, and the contact details you choose to publish — phone, WhatsApp, Facebook and Instagram. These are shown to every visitor on the product page.',
    'privacy.collect.listing':
      'The listing details a merchant writes: condition, battery health, any damage, warranty length and notes. They are published as written.',
    'privacy.collect.photos':
      'Listing photos a merchant uploads. We keep the picture and nothing else: every upload is re-encoded, so no capture location, device serial or timestamp survives.',
    'privacy.collect.wishlist':
      'Your wishlist and price alerts: which product you saved, and the price at which you want to hear from us.',
    'privacy.collect.support':
      'Support messages: the address you type into the form, the subject, and the message itself.',
    'privacy.collect.sessions':
      'Sign-in records: when each session started and ended. The server also writes your IP address and your account number to its logs when you sign in, register, or reset your password.',
    'privacy.collect.provider':
      'If you sign in with Google or Apple: a permanent identifier the provider gives us, and your email address. We never ask for or receive your name or your picture — the only scope we request is your email.',
    'privacy.collect.linkPassword':
      'And if an account with a password already exists on the same address but that address was never confirmed, signing in with a provider links the two, clears that old password and ends its sessions. The reason: it was set by someone who never proved they own the mailbox. You can set a new one through “Forgot password”.',

    'privacy.why.title': 'Why we keep it',
    'privacy.why.signin': 'To sign you in and keep you signed in across page loads.',
    'privacy.why.alerts':
      'To tell you when a product you follow drops in price, and to send confirmation and password-reset links.',
    'privacy.why.shop': 'To show a shop’s details to shoppers so they can reach it.',
    'privacy.why.support': 'To answer your messages.',
    'privacy.why.abuse':
      'To protect the site: we count attempts from each address so passwords cannot be guessed by repetition.',
    'privacy.why.noSale':
      'We do not sell or rent your data, we do not use it for advertising, and there is no ad network on this site.',

    'privacy.not.title': 'What we deliberately do not collect',
    'privacy.not.intro': 'These are decisions in how the site was built, not oversights:',
    'privacy.not.analytics':
      'There is no analytics or tracking service, no advertising pixel, and no session recording. Nothing on this site is loaded from an analytics company.',
    'privacy.not.search':
      'We keep no record of what you searched for. The text of a search reaches our cache only as an unreadable fingerprint, and is erased after five minutes.',
    'privacy.not.taps':
      'When you press Call or WhatsApp we record four things: which shop, which product, which channel, and when. No IP address, no account number, no session identifier.',
    'privacy.not.exif':
      'We do not keep the hidden data inside photos. Every upload is decoded and written afresh, which destroys the capture location, the device and the time it was taken.',
    'privacy.not.sensors':
      'We never ask for your location, your camera or your microphone, and the site explicitly instructs your browser to refuse those requests.',
    'privacy.not.tapsWhy':
      'We count taps because a merchant needs to know whether the site is doing anything for them. The price we accepted for not recording who you are is that we cannot tell two people apart: press twice and it counts twice. That is why we say taps, and never calls or sales — we do not know those.',

    'privacy.cookies.title': 'Cookies and browser storage',
    'privacy.cookies.one':
      'We set exactly one cookie, refresh_token, and only once you sign in. Its only job is to keep you signed in across page loads. No code on the page can read it, it is sent only to the sign-in path, it lasts seven days, and logging out deletes it.',
    'privacy.cookies.local':
      'Your browser also remembers two things you chose by clicking: your language, and light or dark mode. Both stay on your device and never reach our server.',
    'privacy.cookies.oauth':
      'And a second, short-lived cookie, created only when you begin a Google or Apple sign-in and deleted the moment it finishes. Its job is to prove the sign-in that came back is the one your browser started rather than someone else’s. It lasts ten minutes.',
    'privacy.cookies.noBanner1': 'That is why there is no cookie consent banner here.',
    'privacy.cookies.noBanner2':
      'The one cookie is necessary to sign you in, and consent is not asked for what a service needs to work. Your language and theme are your own choices, carry no identifier, and never leave your device. There is no third thing tracking you.',
    'privacy.cookies.noBanner3':
      'A banner here would imply tracking that does not happen, and would train you to press Accept without reading. If we ever add something that does track you, we will ask first.',

    'privacy.others.title': 'Who else sees anything',
    'privacy.others.intro': 'We keep this list as short as we can, but it is not empty:',
    'privacy.others.images':
      'Product photos come from the shops’ own servers, and your browser fetches them directly. So the shop — and whichever hosting company it uses — sees your IP address and which browser you are on. This is the most important line on this page.',
    'privacy.others.referrer':
      'We ask your browser not to tell them which page you were on, so they cannot see which product you were looking at. The IP address cannot be hidden while we are showing you their picture.',
    'privacy.others.meta':
      'The WhatsApp, Facebook and Instagram buttons hand you to Meta. What happens after the tap is governed by their policies, not ours.',
    'privacy.others.email':
      'Our email — confirmation, password resets, price alerts and support replies — goes through the mail provider Brevo, which sees your address and the message. Brevo also rewrites the links in those emails so a click passes through it first and it knows the link was opened, and our current plan does not allow switching that off. That is why password-reset links expire within an hour.',
    'privacy.others.hosting':
      'The database, the cache and the server logs run at hosting providers, who can technically reach them by virtue of running them.',
    'privacy.others.providers':
      'The “Continue with Google” or “Sign in with Apple” button sends your browser to Google or Apple, and our server then exchanges a code with them to confirm who you are. This happens only for someone who presses that button: a visitor who is just comparing prices sends them nothing.',
    'privacy.others.fonts':
      'The fonts and every other file of this site come from our own server. None of it is loaded from Google Fonts or any other external network. That is about the files alone: if you choose to sign in with Google, Google is a party to that, as described above.',
    'privacy.others.retailers':
      'The shop prices we read automatically are fetched by our server on a schedule, not by your browser. Your visit is never reported to them by us.',

    'privacy.keep.title': 'How long we keep it',
    'privacy.keep.honest':
      'Honestly: there is no automatic deletion yet. Most records stay until you delete them, or until we delete them by hand when you ask. We are not going to promise you a retention period the code does not keep.',
    'privacy.keep.wishlist':
      'Wishlist and price alerts: until you remove them or your account is deleted.',
    'privacy.keep.links':
      'Email links: a confirmation link expires within twenty-four hours and a password-reset link within one hour, and each works only once. A record that a link was sent remains.',
    'privacy.keep.sessions':
      'Sign-in sessions: they expire after seven days, and a record that a session began and ended remains.',
    'privacy.keep.support':
      'Support messages: the text is kept even after an account is deleted, because the message is what explains why we did something. The address in it is replaced when you delete your account.',
    'privacy.keep.prices':
      'Price history is kept indefinitely, but it is about products, not about people.',
    'privacy.keep.logs':
      'Server logs are held by the hosting provider under its own settings, and nothing in our code deletes them after a set period.',

    'privacy.rights.title': 'Your rights, and how to use them',
    'privacy.rights.intro':
      'Under Personal Data Protection Law No. 24 of 2023 you have the right to know what we hold about you, to correct it, to ask us to delete it, and to object to how it is used.',
    'privacy.rights.delete':
      'Deleting your account: from your account page, and it is final. It removes your account, your sign-in sessions, your pending links, your wishlist and your alerts. If you are a merchant, your shop comes off the site with its name and contact details erased, and your listing photos are deleted.',
    'privacy.rights.providerLink':
      'Your Google or Apple link: deleting your account removes it on our side. The permission you granted stays in your account with them, so remove this site from your Google or Apple account settings if you want the connection gone entirely.',
    'privacy.rights.survives':
      'What survives deletion: the text of support messages you sent, with the address in them replaced by a code the address cannot be read back out of. Price history and tap counts stay too — those are about products and shops, not about you.',
    'privacy.rights.export':
      'There is not yet a page to download a copy of your data, or to change the address on an account. Write to us and a person will do it by hand.',
    'privacy.rights.accountLink': 'Open your account page to delete your account',
    'privacy.rights.how':
      'For any of these, use the contact page or the address given at the top of this page.',

    'privacy.security.title': 'How we protect your account',
    'privacy.security.password':
      'Your password is never stored as you typed it, but as a hash that is deliberately slow to compute. We never send a password by email: a reset link expires and works once.',
    'privacy.security.cookie':
      'No code on the page can read the session cookie, and the sign-in token is never stored in your browser.',
    'privacy.security.uploads':
      'Every uploaded photo is written afresh before it is stored, so a harmful file cannot travel disguised as a picture.',
    'privacy.security.rate':
      'We limit how many sign-in and registration attempts one address can make.',
    'privacy.security.https':
      'We instruct your browser to reach this site only over an encrypted connection.',
    'privacy.security.honest':
      'We cannot promise you that nothing will ever break. But if a breach touches your data, we will tell the people affected and the authority.',

    'privacy.changes.title': 'If this page changes',
    'privacy.changes.p1':
      'If we change something, we change the date at the top with it. And if the change is material — if we start collecting something new — we will say so plainly on the site, not in a line buried here.',

    'privacy.contact.title': 'How to reach us',
    'privacy.contact.p1':
      'Any question about this page, or any request about your data, can go through the contact page or to the address given at the top. We reply to whatever address you write from.',
    'privacy.contact.link': 'Open the contact page',

    // --- Terms of use. Two audiences at once; see the Arabic table.
    'terms.title': 'Terms of use',
    'terms.blurb': 'What this service does and does not do — for shoppers and for shops.',

    'terms.what.title': 'What this service is',
    'terms.what.p1':
      'Ahsan Se3r compares the price of devices sold by Jordanian shops, and points you at where to find them cheapest.',
    'terms.what.p2':
      'We are not a shop. We sell nothing, and no purchase and no payment happens on this site. When you decide to buy, you deal with the shop directly: the sale, the price, the receipt, the warranty and the return are between you and them, and we are not a party to any of it.',
    'terms.what.p3':
      'Using the site means you accept what is on this page. If you do not accept it, do not use the site.',

    'terms.prices.title': 'About the prices you see',
    'terms.prices.sources':
      'Prices here come from two places: prices we read automatically from shops’ public pages, and prices a merchant enters themselves.',
    'terms.prices.stale':
      'A price here may be old or wrong. Shops change prices at any moment, a merchant can mistype, and we can misread a page.',
    'terms.prices.governs':
      'The price that counts is the shop’s own price at the time you buy. What you see here is a guide, not a promise.',
    'terms.prices.age':
      'We show when each price was last checked, so look at that date before relying on it.',
    'terms.prices.matching':
      'We try to match a shop’s listing to the same product, and we show how close the match is. A close match is not necessarily the same item: check the storage, the colour and the condition before you buy.',
    'terms.prices.report':
      'If you find a wrong price, tell us and we will correct it — but we cannot make a shop honour a price that appeared here.',

    'terms.account.title': 'Your account',
    'terms.account.email':
      'You need a real email address that you can receive mail on, because confirmation, password resets and alerts all go there.',
    'terms.account.password':
      'Your password is your responsibility. Do not share it, and what happens from your account counts as yours.',
    'terms.account.breach':
      'If you think someone else has got into your account, change your password and write to us immediately.',
    'terms.account.one':
      'One account per person or shop. Do not open extra accounts to get around a limit or a suspension.',

    'terms.merchant.title': 'If you are a merchant',
    'terms.merchant.intro': 'When you list something on Ahsan Se3r, you agree to this:',
    'terms.merchant.accurate':
      'That the listing is real: a device you actually have, at a price you will actually sell at, and that you will update it when it changes or sells.',
    'terms.merchant.condition':
      'That you describe the condition honestly: new, used or refurbished, the battery health, and any damage — including damage the photo does not show.',
    'terms.merchant.public':
      'That your contact details — phone, WhatsApp and your social accounts — are published on the product page for every visitor, not only for whoever asks.',
    'terms.merchant.freeText':
      'That your free text — the shop name, the damage notes and the listing notes — is published exactly as written. Do not type anything into it that you do not want published.',
    'terms.merchant.photos':
      'That a photo you upload is yours: you took it, or you have the right to use it, and it is of the actual unit you are selling. Do not upload a photo taken from another shop or from the manufacturer’s site unless you are entitled to.',
    'terms.merchant.licence':
      'That you let us show your listing photos on the site for as long as the listing stands. The photo stays yours, and deleting it here deletes it from us.',
    'terms.merchant.remove':
      'That you may ask for your shop, or any listing in it, to be removed at any time, and we will do it.',
    'terms.merchant.review':
      'We review every shop before its prices become visible to shoppers. We may hide or remove any listing that is misleading, wrong, or against the law, and we will tell you why.',
    'terms.merchant.taps':
      'We show you how many times someone pressed Call or WhatsApp on your listings. That is a count of taps and nothing more: we do not know whether the phone rang, or whether anything was sold, and one person pressing twice counts twice. Do not read those numbers as customers or as sales.',

    'terms.retailers.title': 'For the shops whose prices we read',
    'terms.retailers.p1':
      'We read only publicly published pages, slowly, identifying ourselves on every request, and we honour robots.txt.',
    'terms.retailers.p2':
      'That is courtesy, not a claim that anyone gave us permission. There is no partnership and no agreement between us and these shops.',
    'terms.retailers.p3':
      'If you run one of them and do not want your prices shown here, write to us and we will take them down.',

    'terms.use.title': 'What you may not do here',
    'terms.use.harvest':
      'Harvest merchants’ numbers or details from the site to use for marketing or unwanted messages.',
    'terms.use.copy':
      'Copy the site’s content automatically, or republish it as a competing service.',
    'terms.use.attack':
      'Try to break the site, get into someone else’s account, or work around the usage limits.',
    'terms.use.illegal':
      'Publish anything unlawful, or anything belonging to another person without their permission.',

    'terms.termination.title': 'Closing an account',
    'terms.termination.you':
      'You can delete your account yourself at any time from your account page. Deleting a merchant account hides its prices from the site.',
    'terms.termination.link': 'Open your account page',
    'terms.termination.us':
      'We may suspend or close an account that breaks these terms, and we will say why wherever we can. What survives deletion is set out in the privacy policy.',
    'terms.termination.privacyLink': 'Read the privacy policy',

    'terms.warranty.title': 'No warranty',
    'terms.warranty.p1':
      'The site is provided as it is. We do not promise that it will always work, or that everything on it is correct, complete or up to date.',
    'terms.warranty.p2':
      'We are not responsible for a deal you made with a shop, a price you paid, a device you bought, or how a shop treated you. Nothing on this page or on this site is a warranty of any kind.',
    'terms.warranty.p3':
      'To the extent the law allows, we are not liable for indirect loss arising from your use of the site.',

    'terms.changes.title': 'Changes to these terms',
    'terms.changes.p1':
      'We may change these terms. The date of the last change is at the top, and continuing to use the site after it means you accept it. If a change matters to merchants, we will tell them.',

    'terms.law.title': 'Governing law',
    'terms.law.p1':
      'These terms are governed by the law of the country named at the top of this page, and any dispute goes to its courts.',
    'terms.law.p2':
      'Personal data is governed by Jordan’s Personal Data Protection Law No. 24 of 2023.',

    'terms.contact.title': 'Questions',
    'terms.contact.p1':
      'Any question about these terms, or a request to remove a listing or a shop, can go through the contact page.',
    'terms.contact.link': 'Open the contact page',
  },
};

export default translations;

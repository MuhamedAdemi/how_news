from django import template

register = template.Library()

# Gjuha: kodi → emër sipas gjuhës së UI
LANG_NAMES = {
    "sq": {"sq": "Shqip",         "mk": "Албански",     "en": "Albanian"},
    "mk": {"sq": "Maqedonisht",   "mk": "Македонски",   "en": "Macedonian"},
    "en": {"sq": "Anglisht",      "mk": "Англиски",     "en": "English"},
}

LANG_FLAGS = {"sq": "🇦🇱", "mk": "🇲🇰", "en": "🇬🇧"}

# Lloji i programit: kodi → emër sipas gjuhës
TYPE_NAMES = {
    "grant":        {"sq": "Grant",        "mk": "Грант",        "en": "Grant"},
    "tender":       {"sq": "Tender",       "mk": "Тендер",       "en": "Tender"},
    "competition":  {"sq": "Konkurs",      "mk": "Конкурс",      "en": "Competition"},
    "law":          {"sq": "Ligj",         "mk": "Закон",        "en": "Law"},
    "announcement": {"sq": "Njoftim",      "mk": "Известување",  "en": "Announcement"},
    "subsidy":      {"sq": "Subvencion",   "mk": "Субвенција",   "en": "Subsidy"},
    "loan":         {"sq": "Kredi",        "mk": "Кредит",       "en": "Loan"},
}

# Statusi: kodi → emër
STATUS_NAMES = {
    "active":   {"sq": "Aktiv",      "mk": "Активен",    "en": "Active"},
    "upcoming": {"sq": "Se shpejti", "mk": "Наскоро",    "en": "Upcoming"},
    "expired":  {"sq": "Skaduar",    "mk": "Истечен",    "en": "Expired"},
}

# Kategori lajmesh — slug → emër sipas gjuhës
CAT_NAMES = {
    "bote":      {"sq": "Botë",      "mk": "Свет",       "en": "World"},
    "ekonomi":   {"sq": "Ekonomi",   "mk": "Економија",  "en": "Economy"},
    "kulture":   {"sq": "Kulturë",   "mk": "Култура",    "en": "Culture"},
    "politike":  {"sq": "Politikë",  "mk": "Политика",   "en": "Politics"},
    "shendetesi":{"sq": "Shëndetësi","mk": "Здравство",  "en": "Health"},
    "shoqeri":   {"sq": "Shoqëri",   "mk": "Општество",  "en": "Society"},
    "sport":     {"sq": "Sport",     "mk": "Спорт",      "en": "Sport"},
    "teknologji":{"sq": "Teknologji","mk": "Технологија","en": "Technology"},
}


@register.filter
def lang_name(lang_code, ui_lang="sq"):
    """{{ article.language|lang_name:cur_lang }} → 'Macedonian' / 'Македонски' / 'Maqedonisht'"""
    return LANG_NAMES.get(lang_code, {}).get(ui_lang, lang_code)


@register.filter
def lang_flag(lang_code):
    """{{ article.language|lang_flag }} → '🇲🇰'"""
    return LANG_FLAGS.get(lang_code, "")


@register.filter
def type_name(type_code, ui_lang="sq"):
    return TYPE_NAMES.get(type_code, {}).get(ui_lang, type_code)


@register.filter
def status_name(status_code, ui_lang="sq"):
    return STATUS_NAMES.get(status_code, {}).get(ui_lang, status_code)


@register.filter
def cat_name(slug, ui_lang="sq"):
    return CAT_NAMES.get(slug, {}).get(ui_lang, slug.title())

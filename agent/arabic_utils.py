"""أدوات تطبيع النصوص العربية ومطابقة المرادفات (خصوصًا فئات الأثاث)
تُستخدم في البحث عشان نتعامل مع صيغ الجمع/المرادفات المختلفة اللي بيكتبها
العميل (زي 'دواليب' بدل 'دولاب')."""

import re

CATEGORY_SYNONYM_GROUPS = [
    {"دولاب", "دواليب", "خزانة", "خزائن"},
    {"سرير", "سراير", "أسرة", "اسرة"},
    {"كنبة", "كنب", "انتريه", "أنتريه", "انتريهات"},
    {"ترابيزة", "ترابيزات", "طاولة", "طاولات"},
    {"مكتب", "مكاتب"},
    {"كرسي", "كراسي"},
    {"بوفيه", "بوفيهات"},
    {"مطبخ", "مطابخ"},
    {"بانكيت", "بانكيتات"},
]


def normalize_arabic(text: str) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    text = text.strip().lower()
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"\s+", " ", text)
    return text


_NORMALIZED_SYNONYM_GROUPS = [
    {normalize_arabic(w) for w in group} for group in CATEGORY_SYNONYM_GROUPS
]


def expand_synonyms(word: str) -> set:
    """يرجع كل الكلمات في نفس مجموعة المرادفات، أو الكلمة نفسها لو مفيش مرادفات معروفة."""
    norm_word = normalize_arabic(word)
    for group in _NORMALIZED_SYNONYM_GROUPS:
        if norm_word in group:
            return set(group)
    return {norm_word}


def find_category_match(text: str, category_keywords: dict) -> str | None:
    """category_keywords: {اسم_الكاتيجوري_بعد_التطبيع: الاسم_الأصلي_في_الداتابيز}
    أول حاجة بيجرب تطابق مباشر (زي القديم)، ولو مفيش، بيوسّع كل كلمة في
    نص العميل بمرادفاتها الشائعة (دواليب <-> دولاب) ويحاول تاني."""
    blob = normalize_arabic(text)

    for norm_keyword, category in category_keywords.items():
        if norm_keyword in blob:
            return category

    words = re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)
    candidate_forms = set()
    for w in words:
        candidate_forms |= expand_synonyms(w)

    for norm_keyword, category in category_keywords.items():
        if norm_keyword in candidate_forms:
            return category
        if len(norm_keyword) > 2 and any(
            norm_keyword in c or c in norm_keyword for c in candidate_forms if len(c) > 2
        ):
            return category

    return None


def keyword_variants(word: str) -> set:
    """أشكال بديلة لكلمة بحث واحدة (فروق الألف/الهمزة/التاء المربوطة + المرادفات)
    عشان نطابق عناوين منتجات مكتوبة بصيغة مختلفة شوية عن اللي كتبه العميل."""
    variants = {word}
    variants.add(word.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا"))
    variants.add(word.replace("ة", "ه"))
    variants.add(word.replace("ى", "ي"))
    variants |= expand_synonyms(word)
    return {v for v in variants if v and len(v) > 1}
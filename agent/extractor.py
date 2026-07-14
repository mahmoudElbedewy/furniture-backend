import json
from .llm_config import vision_llm, light_llm
import re



REQUIRED_FIELDS = [
    "title",
    "category_name",
    "supplier_name",
    "base_price",
    "commission_value",
]

EXTRACTION_PROMPT = """أنت أداة استخراج بيانات منتجات أثاث لموقع HA Furniture. اقرأ النص ووصف الصور واستخرج كل البيانات الممكنة. لو حقل غير موجود أو غير مؤكد، خليه null بدل ما تخترع قيمة.

العمولة (commission_value): مهم جداً! ابحث عنها في النص بدقة. تظهر بأشكال مختلفة:
- "commission_value : 350"
- "commission: 350"
- "عمولة: 350"
- أو أي رقم بجانب كلمة commission/عمولة

أمثلة:
- لو النص فيه "commission_value : 350" → استخرج 350
- لو النص فيه "Base price: 2600, commission_value : 350" → استخرج 350
- لو النص فيه "عمولة: 350" → استخرج 350

لو مش موجودة نهائياً في النص، اتركها null.

ارجع JSON فقط بهذا الشكل تمامًا:

{{
  "title": "اسم المنتج أو null",
  "category_name": "اسم التصنيف (دولاب/أنتريه/مكتب/كرسي...) أو null. إذا طلب الأدمن إنشاء تصنيف جديد، اكتب اسمه هنا.",
  "supplier_name": "اسم المورد أو null",
  "material": "الخامة أو null",
  "color": "اللون أو null",
  "dimensions": "نص الأبعاد كما ورد أو null",
  "base_price": رقم أو null,
  "commission_value": رقم أو null,
  "requires_deposit": true/false,
  "deposit_amount": رقم أو null,
  "deposit_note": "ملاحظة عن الديبوزيت أو null",
  "ships_nationwide": true/false,
  "default_shipping_price": رقم أو null,
  "shipping_rates": [{{"governorate": "اسم المحافظة", "area": "اسم المنطقة أو null", "price": رقم}}],
  "description": "وصف قصير من النص أو null",
  "images": [{{"url": "رابط الصورة", "is_primary": true/false}}]
}}

النص الخام:
{raw_text}

روابط الصور المرفوعة (رتّبها بالترتيب، أول صورة افتراضيًا is_primary=true إلا لو وصفها يقول غير ذلك):
{image_urls_list}

وصف الصور:
{image_descriptions}

تعليمات تصحيح من الأدمن (لو موجودة، دي أولوية مطلقة فوق أي استخراج سابق):
{correction_text}

البيانات المستخرجة سابقًا (لو موجودة، عدّل عليها بناءً على التصحيح فوق، وخلي الباقي كما هو):
{previous_payload}

أرجع JSON فقط بدون أي شرح أو Markdown."""


def describe_images(image_urls):
    descriptions = []
    for url in image_urls:
        msg = vision_llm.invoke(
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "صف هذه الصورة لمنتج أثاث: الخامة، اللون، الشكل، وأي نص ظاهر بالسعر أو الأبعاد أو المحافظات",
                        },
                        {"type": "image_url", "image_url": {"url": url}},
                    ],
                }
            ]
        )
        descriptions.append(msg.content)
    return "\n".join(descriptions)


def _get_missing_fields(data: dict) -> list:
    return [f for f in REQUIRED_FIELDS if not data.get(f)]


def extract_product_data(
    raw_text: str, image_urls=None, previous_payload=None, correction_text=None
) -> dict:
    image_urls = image_urls or []
    image_descriptions = (
        describe_images(image_urls) if image_urls else "لا توجد صور جديدة"
    )

    prompt = EXTRACTION_PROMPT.format(
        raw_text=raw_text or "—",
        image_urls_list=(
            json.dumps(image_urls, ensure_ascii=False) if image_urls else "لا يوجد"
        ),
        image_descriptions=image_descriptions,
        correction_text=correction_text or "لا يوجد",
        previous_payload=(
            json.dumps(previous_payload, ensure_ascii=False)
            if previous_payload
            else "لا يوجد"
        ),
    )

    content = light_llm.invoke(prompt).content.strip()
    if content.startswith("```"):
        content = content.strip("`").lstrip("json").strip()

    try:
        data = json.loads(content)
        data = _cross_check_commission(raw_text, data)
    except json.JSONDecodeError:
        return {
            "_raw_extraction_error": content,
            "missing_fields": REQUIRED_FIELDS,
            "ready_for_approval": False,
        }

    if image_urls and not data.get("images"):
        data["images"] = [
            {"url": u, "is_primary": i == 0} for i, u in enumerate(image_urls)
        ]

    missing = _get_missing_fields(data)
    data["missing_fields"] = missing
    data["ready_for_approval"] = len(missing) == 0
    return data


COMMISSION_REGEX = re.compile(
    r"(?:commission(?:_value)?|عمولة)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE
)


def _cross_check_commission(raw_text: str, data: dict) -> dict:
    """تخفيف جزئي (A8) — مش حل نهائي. الموديلات المجانية بتغلط أحياناً فى
    قراءة العمولة، فبنعمل مطابقة مباشرة بـ regex على النص الخام، ولو الرقم
    مختلف عن رقم الموديل بناخد رقم الـ regex لأنه من غير اجتهاد."""
    if not raw_text:
        return data
    match = COMMISSION_REGEX.search(raw_text)
    if match:
        try:
            regex_value = float(match.group(1).replace(",", ""))
        except ValueError:
            return data
        model_value = data.get("commission_value")
        if model_value is None or float(model_value) != regex_value:
            data["commission_value"] = regex_value
    return data
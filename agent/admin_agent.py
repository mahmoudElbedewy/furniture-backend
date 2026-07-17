import json
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from .llm_config import simple_chat_llm
from .extractor import extract_product_data
from .models import AgentActionRequest
from langchain_core.tools import tool
from asgiref.sync import sync_to_async

ADMIN_SYSTEM_PROMPT = """أنت مساعد إداري ذكي لموقع HA Furniture. تتحدث مع "الأدمن" (صاحب الموقع أو المدير).
مهمتك الأساسية هي مساعدته في إضافة منتجات جديدة لقاعدة البيانات من خلال الصور والنصوص التي يرسلها.

خطوات عملك:
1. اقرأ ما يرسله الأدمن واستخدم أداة `process_product_extraction` لاستخراج البيانات من النصوص والصور.
2. الأداة سترد عليك بحالة البيانات. إذا كان هناك حقول ناقصة (missing_fields) مثل "السعر" أو "العمولة" أو "التصنيف" أو "المورد"، اطلب من الأدمن توفيرها بأسلوب عملي وواضح.
3. لو المنتج له أكتر من مقاس بسعر مختلف (زي 150x200 و180x200)، اسأل الأدمن عن كل مقاس وسعره، والسعر ده بيتبعت زي ما هو نهائي في variants من غير ما تضيف عليه عمولة تانية.
4. إذا أخبرك الأدمن أن تصنيفاً معيناً غير موجود ويريد إنشاءه، مرر اسمه في البيانات وسيقوم النظام بإنشائه.
5. إذا ردت الأداة بأن البيانات جاهزة (ready_for_approval=True) وتم إرسالها لتيليجرام، أخبر الأدمن بنجاح العملية واطلب منه الموافقة من تيليجرام.
6. لا تخترع بيانات من عندك أبدًا. كن مباشراً وعملياً في ردودك على الأدمن.
"""

@tool
def process_product_extraction(admin_text: str, image_urls_json: str, previous_payload_json: str = "{}") -> str:
    """
    يستخرج تفاصيل المنتج من النص والصور.
    admin_text: النص الذي أرسله الأدمن (شرح المنتج أو إكمال للنواقص).
    image_urls_json: قائمة روابط الصور بصيغة JSON string (أو '[]' إذا لم يوجد).
    previous_payload_json: إذا كان هناك بيانات تم استخراجها مسبقاً وما زالت ناقصة، مررها هنا كـ JSON.
    """
    try:
        image_urls = json.loads(image_urls_json)
    except (TypeError, ValueError):
        image_urls = []

    try:
        previous_payload = json.loads(previous_payload_json)
    except (TypeError, ValueError):
        previous_payload = {}

    data = extract_product_data(
        raw_text=admin_text,
        image_urls=image_urls,
        previous_payload=previous_payload,
        correction_text=admin_text if previous_payload else None
    )

    if data.get("ready_for_approval"):
        req = AgentActionRequest.objects.create(
            action_type='add_product',
            payload=data,
            reason="طلب إضافة منتج من الشات الإداري",
            status='pending'
        )
        from telegram_bot.services import notify_admin

        variants = data.get("variants") or []
        variants_text = ""
        if variants:
            lines = "\n".join(
                f"  • {v.get('size_name')}: {v.get('price')} ج" for v in variants
            )
            variants_text = f"\n📐 المقاسات:\n{lines}"

        summary = (
            f"🛋️ طلب إضافة منتج جديد:\n"
            f"الاسم: {data.get('title')}\n"
            f"السعر: {data.get('base_price')} + عمولة {data.get('commission_value')}\n"
            f"التصنيف: {data.get('category_name')}"
            f"{variants_text}"
        )
        notify_admin(
            notification_type="agent_action",
            related_object_id=req.id,
            message=summary,
            buttons=[
                {"text": "✅ موافقة", "callback_data": f"agent_approve:{req.id}"},
                {"text": "❌ رفض", "callback_data": f"agent_reject:{req.id}"},
            ],
        )
        return json.dumps({
            "status": "success",
            "ready_for_approval": True,
            "message": "تم إرسال الطلب بنجاح إلى تيليجرام للموافقة.",
            "extracted_data": data
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "status": "incomplete",
            "ready_for_approval": False,
            "missing_fields": data.get("missing_fields", []),
            "current_payload": data
        }, ensure_ascii=False)


ADMIN_TOOLS = [process_product_extraction]
ADMIN_TOOLS_BY_NAME = {t.name: t for t in ADMIN_TOOLS}
llm_with_admin_tools = simple_chat_llm.bind_tools(ADMIN_TOOLS)


def _message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("message")
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)

    if isinstance(content, dict):
        text = content.get("text") or content.get("content") or content.get("message")
        return str(text) if text else ""

    return "" if content is None else str(content)


async def get_admin_reply(history_messages: list, admin_message: str, image_urls: list = None) -> str:
    """
    history_messages: لسيتة [{'role': 'admin'|'agent', 'content': str}, ...]
    admin_message: رسالة الأدمن الحالية.
    image_urls: صور رفعها الأدمن.
    """
    messages = [SystemMessage(content=ADMIN_SYSTEM_PROMPT)]
    for m in history_messages:
        if m["role"] == "admin":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))
            
    # تضمين الصور إن وجدت كجزء من الرسالة في الـ Prompt الداخلي للأداة
    urls_str = json.dumps(image_urls or [], ensure_ascii=False)
    combined_message = admin_message
    if image_urls:
        combined_message += f"\n[مرفق صور]: {urls_str}"
        
    messages.append(HumanMessage(content=combined_message))

    for _ in range(3):  
        response = await llm_with_admin_tools.ainvoke(messages)
        if not response.tool_calls:
            return _message_content_to_text(response.content)

        messages.append(response)
        for call in response.tool_calls:
            tool_fn = ADMIN_TOOLS_BY_NAME[call["name"]]
            args = call["args"]
            
            # تحديث الروابط تلقائيا إذا نسي النموذج تمريرها وكان هناك صور مرفوعة
            if call["name"] == "process_product_extraction" and image_urls and not args.get("image_urls_json"):
                args["image_urls_json"] = urls_str

            # Wrap sync DB operation
            result = await sync_to_async(tool_fn.invoke)(args)
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    return "برجاء تأكيد البيانات أو مراجعة لوحة التحكم."

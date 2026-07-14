import asyncio
import ast
import random
import re
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from channels.db import database_sync_to_async
from .llm_config import CHAT_LLMS
from .persona_prompt import PERSONA_SYSTEM_PROMPT, DEPOSIT_WHATSAPP
from .tools import (
    search_products,
    show_product_cards,
    escalate_to_admin,
    track_order,
    create_order_from_chat,
    answer_general_policy,
    get_shipping_options,
    check_deposit_requirements,
    get_product_details,
    list_catalog_products,
)
from django.core.cache import cache
from catalog.models import Product, Governorate, Category

TOOLS = [
    search_products,
    show_product_cards,
    escalate_to_admin,
    track_order,
    create_order_from_chat,
    answer_general_policy,
    get_shipping_options,
    check_deposit_requirements,
    get_product_details,
    list_catalog_products,
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

TOOL_LEAK_PATTERNS = [
    r"<function[^>]*>",
    r"</function>",
    r"\bsearch_products\b",
    r"\bget_shipping_options\b",
    r"\bcheck_deposit_requirements\b",
    r"\bcreate_order_from_chat\b",
    r"\bget_product_details\b",
    r"\bshow_product_cards\b",
    r"(هستخدم|هجيب|هشوف|أنا هتستخدم|هستدعي)\s+(أداة|tool|function)",
]

BAD_RESPONSE_PATTERNS = [
    r"ليه\s+(ده|كده|عايز|تعمل|تطلب)",
    r"في\s+حاج[ةه]\s+تاني",
    r"متجاوب",
    r"كيفك\s+ده",
    r"سلمت",
    r"جابنا",
    r"قبل\s+ما\s+(نبد|ابد)",
    r"عايز\s+تعرف",
    r"في\s+كذا\s+موديل",
    r"ليه\s+عايز",
    r"\bAI\b",
    r"\bبوت\b",
]

GREETING_PATTERNS = [
    r"^(اه+لا|أه+لا|السلام\s+عليك|سلام|مرحب|هاي|hi|hello|صباح|مساء)",
    r"^(از+يك|إز+يك|عامل\s+ا?يه)",
]

TRACK_ORDER_PATTERNS = [r"تتبع", r"تراك", r"فين\s+الا?وردر", r"حالة\s+الا?وردر"]

CONFIRM_WORDS = ["تمام", "موافق", "أيوه", "ايوه", "نعم", "انفذ", "نفذ", "ماشي", "اوك", "ok", "yes", "اكيد", "أكيد"]


PHONE_PATTERN = re.compile(r"01[0125][0-9]{8}")
@database_sync_to_async
def _fetch_governorate_names() -> list[str]:
    cached = cache.get("agent_governorate_names_v1")
    if cached is not None:
        return cached
    names = list(Governorate.objects.values_list("name", flat=True))
    cache.set("agent_governorate_names_v1", names, 60 * 30)
    return names


@database_sync_to_async
def _fetch_category_keywords() -> dict:
    cached = cache.get("agent_category_keywords_v1")
    if cached is not None:
        return cached
    mapping = {_normalize_arabic(c.name): c.name for c in Category.objects.all()}
    cache.set("agent_category_keywords_v1", mapping, 60 * 30)
    return mapping


def _strip_emojis(text: str) -> str:
    return EMOJI_PATTERN.sub("", text).strip()


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


def _text_blob(text: str) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    return f"{text.lower().strip()} {_normalize_arabic(text)}"


def _normalize_arabic(text: str) -> str:
    if not isinstance(text, str):
        text = str(text or "")
    text = text.strip().lower()
    text = text.replace("إ", "ا").replace("أ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"\s+", " ", text)
    return text


def _clean_response(text: str) -> str:
    text = _clean_tool_leaks(text)
    return _strip_emojis(text)


def _clean_tool_leaks(text: str) -> str:
    for pattern in TOOL_LEAK_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _looks_like_bad_response(text: str) -> bool:
    if not text or len(text.strip()) < 3:
        return True
    blob = _text_blob(text)
    return any(re.search(p, blob, re.IGNORECASE) for p in BAD_RESPONSE_PATTERNS)


def _is_track_order_intent(text: str) -> bool:
    blob = _text_blob(text)
    return any(re.search(p, blob, re.IGNORECASE) for p in TRACK_ORDER_PATTERNS)


def _is_greeting(text: str) -> bool:
    blob = _text_blob(text)
    if len(blob.split()) > 8 or _is_order_intent(text) or _is_search_intent(text):
        return False
    return any(re.search(p, blob, re.IGNORECASE) for p in GREETING_PATTERNS)


def _is_order_intent(text: str) -> bool:
    if _is_track_order_intent(text):
        return False
    blob = _text_blob(text)
    order_words = ["اورder", "اوردر", "اورد", "order", "طلب", "اطلب"]
    if any(w in blob for w in order_words):
        return True
    if any(w in blob for w in ["عايز", "عاوز", "حابب", "نفسي", "محتاج"]) and re.search(
        r"(اع[mnml]|اشتري|اطلب|اورد|طلب|المنتج|مفتوح|عليه|علي)", blob
    ):
        return True
    return False


def _is_search_intent(text: str) -> bool:
    if _is_track_order_intent(text) or _is_order_intent(text):
        return False
    blob = _text_blob(text)
    search_signals = [
        "دواليب",
        "دولاب",
        "ترابيز",
        "كنب",
        "سرير",
        "بانكيت",
        "بلاط",
        "مطبخ",
        "سعر",
        "تحت",
        "فوق",
        "اقل",
        "أقل",
        "اكثر",
        "أكثر",
        "خامة",
        "لون",
        "مقترح",
        "دور",
        "فيه",
        "موجود",
    ]
    return any(s in blob for s in search_signals)


def _has_order_details(text: str) -> bool:
    has_phone = bool(PHONE_PATTERN.search(text))
    blob = _text_blob(text)
    has_location = len(blob) > 20 and any(
        kw in blob
        for kw in ["محافظ", "عنوان", "شارع", "برج", "القاهر", "اسكندر", "جيز", "مدين", "عمارة", "منطق"]
    )
    return has_phone and has_location


def _agent_awaiting_confirmation(history_messages: list) -> bool:
    for msg in reversed(history_messages[-6:]):
        if msg.get("role") == "agent" and "أنفذ الأوردر" in msg.get("content", ""):
            return True
    return False


def _customer_confirmed_order(customer_message: str, history_messages: list) -> bool:
    if not _agent_awaiting_confirmation(history_messages):
        return False
    words = _normalize_arabic(customer_message).strip().split()
    if not words or len(words) > 3:
        return False
    confirm_normalized = {_normalize_arabic(w) for w in CONFIRM_WORDS}
    return all(w.strip(".!،") in confirm_normalized for w in words)


def _should_collect_order_details(customer_message: str, history_messages: list) -> bool:
    if _is_search_intent(customer_message) or _has_order_details(customer_message):
        return False
    if _agent_awaiting_confirmation(history_messages) or _customer_confirmed_order(
        customer_message, history_messages
    ):
        return False
    return _is_order_intent(customer_message)


def _parse_customer_details(text: str, governorate_names: list[str]) -> tuple[str, str, str, str]:
    phone_match = PHONE_PATTERN.search(text)
    phone = phone_match.group(0) if phone_match else ""

    governorate = ""
    for gov in governorate_names:
        if gov in text or _normalize_arabic(gov) in _normalize_arabic(text):
            governorate = gov
            break

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    if len(lines) > 1:
        name, name_found, address_lines = "عميل", False, []
        for line in lines:
            is_phone_line = bool(PHONE_PATTERN.search(line))
            is_gov_line = bool(governorate) and governorate in line
            if not name_found and not is_phone_line and not is_gov_line:
                name, name_found = line, True
                continue
            if not is_phone_line and not is_gov_line:
                address_lines.append(line)
        address = " - ".join(address_lines) if address_lines else text
        return name, phone, governorate, address

    remaining = text.replace(phone, "").strip() if phone else text.strip()
    parts = remaining.split()
    name = parts[0] if parts else "عميل"
    address = remaining[len(name):].strip() if name in remaining else remaining
    return name, phone, governorate, address

async def _parse_search_params(text: str) -> dict:
    blob = _text_blob(text)
    params = {"query": "", "category": None, "max_price": None, "min_price": None}

    category_keywords = await _fetch_category_keywords()
    for norm_keyword, category in category_keywords.items():
        if norm_keyword in blob:
            params["category"] = category
            params["query"] = category
            break

    max_match = re.search(r"(?:تحت|اقل|أقل|اقل\s+من|less\s+than|below)\s*(\d+)", blob)
    if max_match:
        params["max_price"] = float(max_match.group(1))
    min_match = re.search(r"(?:فوق|اكتر|أكثر|more\s+than|above)\s*(\d+)", blob)
    if min_match:
        params["min_price"] = float(min_match.group(1))
    if not params["query"]:
        params["query"] = text.strip()[:50]

    return {k: v for k, v in params.items() if v is not None}

def _parse_shipping_price(shipping_str: str) -> tuple[float, str]:
    try:
        data = ast.literal_eval(shipping_str)
        if isinstance(data, dict):
            for _title, options in data.items():
                if options and isinstance(options, list):
                    first = options[0]
                    return float(first.get("price", 0)), str(first.get("location", ""))
    except (SyntaxError, ValueError, TypeError):
        pass
    return 0.0, ""


def _parse_deposit_info(deposit_str: str) -> tuple[bool, float, str]:
    if "لا يوجد" in deposit_str:
        return False, 0.0, ""
    try:
        data = ast.literal_eval(deposit_str)
        if isinstance(data, list):
            for item in data:
                if item.get("requires_deposit"):
                    return True, float(item.get("deposit_amount", 0)), str(
                        item.get("deposit_note", "")
                    )
    except (SyntaxError, ValueError, TypeError):
        pass
    return False, 0.0, ""


def _find_details_message(history_messages: list) -> str | None:
    for msg in reversed(history_messages):
        if msg.get("role") == "customer" and _has_order_details(msg.get("content", "")):
            return msg.get("content", "")
    return None


def _build_greeting_reply(context_data: dict | None) -> str:
    product_name = (context_data or {}).get("product_name")
    if product_name:
        return (
            f"أهلاً بيك.\n"
            f"أنا كريم من HA Furniture.\n"
            f"شايف إنك بتتفرج على {product_name}.\n"
            f"حابب تعرف تفاصيل أكتر، ولا نعمل أوردر؟"
        )
    return (
        "أهلاً بيك.\n"
        "أنا كريم من HA Furniture.\n"
        "قولي محتاج إيه — منتج، شحن، أو أوردر."
    )


def _build_order_start_reply(
    context_data: dict | None, product_details: str | None = None
) -> str:
    product_name = (context_data or {}).get("product_name")
    price = None
    if product_details:
        match = re.search(r"السعر:\s*([\d.]+)", product_details)
        if match:
            price = match.group(1)

    lines = ["تمام يا فندم.", "حاضر نعمل الأوردر."]
    if product_name:
        price_part = f" — السعر {price} جنيه" if price else ""
        lines.append(f"\nالمنتج: {product_name}{price_part}")
    lines.append(
        "\nابعتلي:\n"
        "- الاسم الكامل\n"
        "- رقم الموبايل\n"
        "- المحافظة\n"
        "- العنوان بالتفصيل"
    )
    return "\n".join(lines)


async def _handle_product_search(customer_message: str) -> str:
    params = await _parse_search_params(customer_message)
    search_args = {"query": params.get("query", "")}
    if params.get("category"):
        search_args["category"] = params["category"]
    if params.get("max_price") is not None:
        search_args["max_price"] = params["max_price"]
    if params.get("min_price") is not None:
        search_args["min_price"] = params["min_price"]

    results_str = await search_products.ainvoke(search_args)
    if results_str == "لا توجد منتجات مطابقة.":
        return "مافيش منتجات مطابقة لطلبك دلوقتي. جرب تغيير السعر أو نوع المنتج."

    try:
        results = ast.literal_eval(results_str)
    except (SyntaxError, ValueError):
        return "حصلت مشكلة في البحث. جرب تاني."

    if not results:
        return "مافيش منتجات مطابقة لطلبك دلوقتي."

    product_ids = [str(r["id"]) for r in results]
    cards_str = await show_product_cards.ainvoke({"product_ids": product_ids})

    lines = [f"لقيت {len(results)} منتج مناسب:"]
    for item in results[:6]:
        lines.append(f"- {item['title']} — {item['final_price']} جنيه")
    lines.append("")
    lines.append(
        "المنتجات المقترحة ظهرتلك في الشاشة. اضغط على أي منتج يعجبك، "
        "أو قولي عايز تعمل أوردر على أنهي واحد."
    )
    return "\n".join(lines) + "\n\n" + cards_str


async def _build_order_quote(
    customer_message: str, context_data: dict, product_details: str | None
) -> str:
    product_id = str(context_data.get("product_id", ""))
    product_name = context_data.get("product_name", "المنتج")
    governorate_names = await _fetch_governorate_names()
    name, phone, governorate, address = _parse_customer_details(customer_message)

    if not governorate:
        return (
            "تمام يا فندم، استلمت بياناتك.\n"
            "محتاج تأكيد المحافظة بالظبط عشان أحسب الشحن.\n"
            "ابعت المحافظة والعنوان مرة تانية."
        )

    deposit_str = await check_deposit_requirements.ainvoke({"product_ids": [product_id]})
    shipping_str = await get_shipping_options.ainvoke(
        {"product_ids": [product_id], "governorate": governorate}
    )

    product_price = 0.0
    if product_details:
        match = re.search(r"السعر:\s*([\d.]+)", product_details)
        if match:
            product_price = float(match.group(1))
    if not product_price:
        try:
            product = await database_sync_to_async(Product.objects.get)(id=product_id)
            product_price = float(product.final_price)
            product_name = product.title
        except Product.DoesNotExist:
            return "المنتج مش متوفر دلوقتي."

    shipping_price, shipping_location = _parse_shipping_price(shipping_str)
    total = product_price + shipping_price
    has_deposit, deposit_amount, deposit_note = _parse_deposit_info(deposit_str)

    lines = [
        "تمام يا فندم، ده ملخص الأوردر:",
        f"الاسم: {name}",
        f"الموبايل: {phone}",
        f"المحافظة: {governorate}",
        f"العنوان: {address}",
        "",
        f"المنتج: {product_name}",
        f"سعر المنتج: {product_price:.0f} جنيه",
        f"الشحن ({shipping_location or governorate}): {shipping_price:.0f} جنيه",
        f"الإجمالي: {total:.0f} جنيه",
    ]

    if has_deposit and deposit_amount > 0:
        lines.extend(
            [
                "",
                f"الديبوزيت المطلوب: {deposit_amount:.0f} جنيه",
                f"حوّل الديبوزيت على: {DEPOSIT_WHATSAPP}",
                f"وابعت screenshot التحويل على الواتساب: {DEPOSIT_WHATSAPP}",
                "تقدر تتابع معانا من هناك.",
            ]
        )
        if deposit_note:
            lines.append(f"ملاحظة: {deposit_note}")

    lines.extend(["", "أنفذ الأوردر؟"])
    return "\n".join(lines)


async def _execute_confirmed_order(
    conversation, history_messages: list, context_data: dict | None
) -> str:
    details_text = _find_details_message(history_messages)
    if not details_text or not context_data or not context_data.get("product_id"):
        return "محتاج بياناتك الأول: الاسم، الموبايل، المحافظة، والعنوان."

    product_id = str(context_data["product_id"])
    governorate_names = await _fetch_governorate_names()
    name, phone, governorate, address = _parse_customer_details(details_text)

    shipping_str = await get_shipping_options.ainvoke(
        {"product_ids": [product_id], "governorate": governorate}
    )
    shipping_price, shipping_location = _parse_shipping_price(shipping_str)

    result = await create_order_from_chat.ainvoke(
        {
            "customer_name": name,
            "customer_phone": phone,
            "governorate": governorate,
            "address": address,
            "product_ids": [product_id],
            "shipping_total": shipping_price,
            "shipping_location": shipping_location or governorate,
            "conversation_id": str(conversation.id),
        }
    )

    return _clean_response(f"تمام يا فندم.\n{result}\n\nهنتواصل معاك قريب.")


@database_sync_to_async
def _fetch_product_details(product_id: str) -> str | None:
    try:
        product = Product.objects.get(id=product_id, is_available=True)
        return (
            f"المنتج: {product.title}\n"
            f"ID: {product.id}\n"
            f"السعر: {product.final_price} جنيه\n"
            f"التصنيف: {product.category.name if product.category else 'غير محدد'}\n"
            f"ديبوزيت: {'نعم - ' + str(product.deposit_amount) + ' جنيه' if product.requires_deposit and product.deposit_amount else 'لا'}"
        )
    except Product.DoesNotExist:
        return None


@database_sync_to_async
def _fetch_catalog_summary() -> str:
    cached = cache.get("agent_catalog_summary_v1")
    if cached is not None:
        return cached
    products = Product.objects.filter(is_available=True).select_related("category")[:80]
    summary = (
        "لا توجد منتجات."
        if not products
        else "\n".join(f"- {p.title} | {p.final_price}ج | id={p.id}" for p in products)
    )
    cache.set("agent_catalog_summary_v1", summary, 60 * 10)
    return summary


def _build_history_messages(history_messages: list):
    messages = []
    for m in history_messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if not content or content.startswith("[System Note:"):
            continue
        if role == "agent" and _looks_like_bad_response(content):
            continue
        if role == "customer":
            messages.append(HumanMessage(content=content))
        elif role == "admin":
            messages.append(HumanMessage(content=f"[رسالة من الإدارة]: {content}"))
        else:
            messages.append(AIMessage(content=content))
    return messages


def _build_llm_with_tools(llm):
    return llm.bind_tools(TOOLS)


async def _invoke_llm(messages):
    for llm in CHAT_LLMS:
        try:
            response = await _build_llm_with_tools(llm).ainvoke(messages)
            if response.tool_calls:
                return response
            text = _clean_response(_message_content_to_text(response.content))
            if text and not _looks_like_bad_response(text):
                return response
        except Exception as e:
            print(f"LLM invoke error ({llm.__class__.__name__}): {e}")
    return None


async def get_agent_reply(
    conversation, history_messages: list, customer_message: str, context_data: dict = None
) -> str:
    await asyncio.sleep(random.uniform(0.5, 1.0))

    if _is_search_intent(customer_message):
        return _clean_response(await _handle_product_search(customer_message))

    if _customer_confirmed_order(customer_message, history_messages):
        return await _execute_confirmed_order(conversation, history_messages, context_data)

    if _agent_awaiting_confirmation(history_messages) and not _customer_confirmed_order(
        customer_message, history_messages
    ):
        if not _is_search_intent(customer_message):
            return "محتاج تأكيد منك: أنفذ الأوردر؟ قولي تمام أو موافق."

    product_details = None
    if context_data and context_data.get("product_id"):
        product_details = await _fetch_product_details(context_data["product_id"])

    if (
        _has_order_details(customer_message)
        and context_data
        and context_data.get("product_id")
    ):
        return await _build_order_quote(customer_message, context_data, product_details)

    if _should_collect_order_details(customer_message, history_messages):
        return _build_order_start_reply(context_data, product_details)

    if _is_greeting(customer_message):
        return _build_greeting_reply(context_data)

    system_content = PERSONA_SYSTEM_PROMPT + f"\n\n## المنتجات:\n{await _fetch_catalog_summary()}"
    if product_details:
        system_content += f"\n\n## المنتج المفتوح:\n{product_details}"

    messages = [SystemMessage(content=system_content)]
    messages.extend(_build_history_messages(history_messages))
    messages.append(HumanMessage(content=customer_message))

    tools_called: set[str] = set()

    for _ in range(8):
        response = await _invoke_llm(messages)
        if response is None:
            return _build_order_start_reply(context_data, product_details)

        if not response.tool_calls:
            text = _clean_response(_message_content_to_text(response.content))
            if _looks_like_bad_response(text):
                return _build_order_start_reply(context_data, product_details)
            return text or _build_order_start_reply(context_data, product_details)

        messages.append(response)
        for call in response.tool_calls:
            tool_name = call["name"]
            tool_fn = TOOLS_BY_NAME.get(tool_name)
            if not tool_fn:
                continue

            if tool_name == "create_order_from_chat":
                if not _customer_confirmed_order(customer_message, history_messages):
                    messages.append(
                        ToolMessage(
                            content="Error: must show quote and get customer confirmation (أنفذ الأوردر؟) before creating order.",
                            tool_call_id=call["id"],
                        )
                    )
                    continue

            args = dict(call["args"])
            if tool_name == "escalate_to_admin":
                args["conversation_id"] = str(conversation.id)
            if tool_name == "create_order_from_chat":
                args["conversation_id"] = str(conversation.id)

            try:
                result = await tool_fn.ainvoke(args)
                tools_called.add(tool_name)
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=call["id"])
                )
            except Exception as e:
                messages.append(
                    ToolMessage(
                        content=f"Error: {str(e)}",
                        tool_call_id=call["id"],
                    )
                )

    return _build_order_start_reply(context_data, product_details)

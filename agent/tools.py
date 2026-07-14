from decimal import Decimal
from langchain_core.tools import tool
from channels.db import database_sync_to_async
from catalog.models import Product
from chat.models import ChatConversation
from orders.models import Order, OrderItem
from django.db import transaction
from orders.models import Order, OrderItem, Commission


def _build_order_telegram_message(order) -> tuple[str, list]:
    lines = []
    for item in order.items.select_related("product").all():
        product = item.product
        item_shipping = item.shipping_price or 0
        item_location = item.shipping_location or "غير محدد"
        description = product.description or "لا يوجد وصف"
        lines.append(
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>{product.title}</b> x{item.quantity}\n"
            f"📝 الوصف: {description}\n"
            f"💰 السعر قبل العمولة: {product.base_price} ج\n"
            f"💵 العمولة: {product.commission_value} ج\n"
            f"💲 السعر بعد العمولة: {item.price_at_order_time} ج\n"
            f"🚚 الشحن: {item_shipping} ج\n"
            f"📍 مكان الشحن: {item_location}"
        )

    items_text = "\n\n".join(lines) or "لا توجد عناصر"
    message = (
        f"🛒 <b>أوردر جديد (من الشات)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 رقم الأوردر: {order.order_number}\n"
        f"👤 العميل: {order.customer_name}\n"
        f"📱 رقم الهاتف: {order.customer_phone}\n"
        f"📍 المحافظة: {order.customer_governorate}"
        + (f" - {order.customer_area}" if order.customer_area else "")
        + "\n"
        f"🏠 العنوان: {order.customer_address}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📦 المنتجات:\n\n{items_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🚚 تكلفة الشحن: {order.shipping_price} ج\n"
        f"💵 الإجمالي: {order.total_price} ج"
    )
    buttons = [
        {"text": "✅ موافقة", "callback_data": f"order_approve:{order.order_number}"},
        {"text": "❌ رفض", "callback_data": f"order_reject:{order.order_number}"},
    ]
    return message, buttons


def _send_order_telegram(order):
    try:
        from telegram_bot.services import notify_admin

        message, buttons = _build_order_telegram_message(order)
        notify_admin("new_order", order.id, message, buttons=buttons)
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")


@tool
async def list_catalog_products() -> str:
    """يرجع قائمة بكل المنتجات المتاحة في الموقع مع الأسعار والتصنيفات وIDs.
    استخدمها لما العميل يسأل عن المنتجات المتاحة أو محتاج تعرف إيه الموجود."""

    @database_sync_to_async
    def _list():
        products = Product.objects.filter(is_available=True).select_related("category")
        results = []
        for p in products:
            results.append(
                {
                    "id": str(p.id),
                    "title": p.title,
                    "final_price": float(p.final_price),
                    "category": p.category.name if p.category else "",
                    "requires_deposit": p.requires_deposit,
                    "deposit_amount": float(p.deposit_amount or 0),
                    "default_shipping_price": float(p.default_shipping_price or 0),
                }
            )
        return str(results)

    return await _list()


@tool
async def search_products(
    query: str,
    category: str = None,
    min_price: float = None,
    max_price: float = None,
    material: str = None,
    color: str = None,
    has_deposit: bool = None,
) -> str:
    """يبحث عن منتجات أثاث متوفرة في الموقع حسب كلمة بحث وفلاتر اختيارية."""

    @database_sync_to_async
    def _search():
        qs = Product.objects.filter(is_available=True)
        if query:
            qs = qs.filter(title__icontains=query) | qs.filter(
                description__icontains=query
            )
        if category:
            qs = qs.filter(category__name__icontains=category)
        if min_price:
            qs = qs.filter(final_price__gte=min_price)
        if max_price:
            qs = qs.filter(final_price__lte=max_price)
        if material:
            qs = qs.filter(material__icontains=material)
        if color:
            qs = qs.filter(color__icontains=color)
        if has_deposit is not None:
            qs = qs.filter(requires_deposit=has_deposit)
        return list(
            qs[:10].values(
                "id",
                "title",
                "slug",
                "final_price",
                "material",
                "color",
                "requires_deposit",
                "deposit_amount",
                "deposit_note",
                "ships_nationwide",
                "default_shipping_price",
            )
        )

    results = await _search()
    if not results:
        return "لا توجد منتجات مطابقة."
    return str(results)


@tool
async def show_product_cards(product_ids: list[str]) -> str:
    """يعرض كروت منتجات للعميل في الشات بناءً على IDs منتجات."""

    @database_sync_to_async
    def _fetch():
        qs = Product.objects.filter(id__in=product_ids, is_available=True)
        return list(
            qs.values(
                "id",
                "title",
                "slug",
                "final_price",
                "requires_deposit",
                "deposit_amount",
            )
        )

    cards = await _fetch()
    ids_str = ",".join([str(c["id"]) for c in cards])
    return str(
        {
            "action": "render_product_cards",
            "api_endpoint": f"/api/catalog/product-cards/?ids={ids_str}",
            "products_count": len(cards),
        }
    )


@tool
async def escalate_to_admin(
    conversation_id: str, situation_summary: str, suggested_reply: str
) -> str:
    """يصعّد المحادثة للأدmin عبر تليجرام."""

    @database_sync_to_async
    def _escalate():
        conv = ChatConversation.objects.get(id=conversation_id)
        conv.escalation_note = (
            f"الموقف: {situation_summary}\nاقتراح للرد: {suggested_reply}"
        )
        conv.status = "needs_admin"
        conv.is_agent_active = False
        conv.save()

    await _escalate()
    return "تم التصعيد للأدمن."


@tool
async def track_order(order_number: str) -> str:
    """يتتبع حالة الأوردر للعميل باستخدام رقم الأوردر."""

    @database_sync_to_async
    def _track():
        try:
            order = Order.objects.get(order_number__iexact=order_number.strip())
            items = order.items.all()
            items_text = ", ".join(
                [f"{item.product.title} (x{item.quantity})" for item in items]
            )
            deposit_info = ""
            for item in items:
                if item.product.requires_deposit and item.product.deposit_amount:
                    deposit_info += f"\n⚠️ المنتج '{item.product.title}' عليه ديبوزيت {item.product.deposit_amount} جنيه."
            return (
                f"الأوردر رقم {order.order_number} موجود.\n"
                f"الحالة: {order.get_status_display()}\n"
                f"المنتجات: {items_text}\n"
                f"الإجمالي: {order.total_price} جنيه"
                f"{deposit_info}"
            )
        except Order.DoesNotExist:
            return "عذراً، لم أتمكن من العثور على أوردر بهذا الرقم."

    return await _track()


@tool
async def get_shipping_options(product_ids: list[str], governorate: str = None) -> str:
    """يحصل على خيارات الشحن المتاحة للمنتجات المختارة بناءً على المحافظة.
    ⚠️ إلزامي قبل ذكر أي سعر شحن أو إنشاء أوردر."""

    @database_sync_to_async
    def _get_options():
        products = Product.objects.filter(id__in=product_ids, is_available=True)
        if not products.exists():
            return "عذراً، المنتجات غير متوفرة."

        options = {}
        for product in products:
            rates = product.shipping_rates.select_related("governorate", "area").all()
            if governorate:
                rates = rates.filter(governorate__name__icontains=governorate)

            if rates.exists():
                product_options = []
                for rate in rates:
                    location = f"{rate.governorate.name}"
                    if rate.area:
                        location += f" - {rate.area.name}"
                    product_options.append(
                        {"location": location, "price": float(rate.price)}
                    )
                options[product.title] = product_options
            elif product.default_shipping_price is not None:
                options[product.title] = [
                    {
                        "location": "السعر الافتراضي",
                        "price": float(product.default_shipping_price),
                    }
                ]
            else:
                options[product.title] = [{"location": "شحن مجاني", "price": 0}]

        return str(options)

    return await _get_options()


@tool
async def check_deposit_requirements(product_ids: list[str]) -> str:
    """يفحص هل المنتجات المختارة عليها ديبوزيت ولا لا.
    ⚠️ إلزامي قبل ذكر كلمة ديبوزيت أو عربون أو إنشاء أوردر."""

    @database_sync_to_async
    def _check():
        products = Product.objects.filter(id__in=product_ids, is_available=True)
        if not products.exists():
            return "عذراً، المنتجات غير متوفرة."

        results = []
        has_deposit = False
        for product in products:
            if product.requires_deposit and product.deposit_amount:
                has_deposit = True
                results.append(
                    {
                        "product": product.title,
                        "requires_deposit": True,
                        "deposit_amount": float(product.deposit_amount),
                        "deposit_note": product.deposit_note or "",
                    }
                )
            else:
                results.append(
                    {
                        "product": product.title,
                        "requires_deposit": False,
                        "deposit_amount": 0,
                        "deposit_note": "",
                    }
                )

        if not has_deposit:
            return "لا يوجد منتجات عليها ديبوزيت. ممنوع تذكر الديبوزيت للعميل إطلاقاً."

        return str(results)

    return await _check()


@tool
async def get_product_details(product_id: str) -> str:
    """يجيب كل تفاصيل المنتج من قاعدة البيانات — إلزامي لما تعرف product_id."""

    @database_sync_to_async
    def _get_details():
        try:
            product = Product.objects.get(id=product_id, is_available=True)
            shipping_rates = []
            for rate in product.shipping_rates.select_related(
                "governorate", "area"
            ).all()[:20]:
                loc = rate.governorate.name
                if rate.area:
                    loc += f" - {rate.area.name}"
                shipping_rates.append({"location": loc, "price": float(rate.price)})

            details = {
                "id": str(product.id),
                "title": product.title,
                "slug": product.slug,
                "base_price": float(product.base_price),
                "final_price": float(product.final_price),
                "commission_value": float(product.commission_value),
                "material": product.material or "غير محدد",
                "color": product.color or "غير محدد",
                "dimensions": product.dimensions or "غير محدد",
                "description": product.description or "لا يوجد وصف",
                "requires_deposit": product.requires_deposit,
                "deposit_amount": (
                    float(product.deposit_amount) if product.deposit_amount else 0
                ),
                "deposit_note": product.deposit_note or "",
                "default_shipping_price": (
                    float(product.default_shipping_price)
                    if product.default_shipping_price
                    else 0
                ),
                "shipping_rates": shipping_rates,
                "category": product.category.name if product.category else "غير محدد",
            }
            return str(details)
        except Product.DoesNotExist:
            return "عذراً، المنتج غير موجود أو غير متوفر."

    return await _get_details()


@tool
async def create_order_from_chat(
    customer_name: str,
    customer_phone: str,
    governorate: str,
    address: str,
    product_ids: list[str],
    shipping_total: float = 0,
    shipping_location: str = "",
    conversation_id: str = None,
) -> str:
    """ينشئ أوردر جديد للعميل بعد تجميع بياناته كاملة.
    ⚠️ لازم تكون استخدمت check_deposit_requirements و get_shipping_options قبلها."""

    @database_sync_to_async
    def _create():
        products = list(Product.objects.filter(id__in=product_ids, is_available=True))
        if not products:
            return "عذراً، المنتجات المطلوبة غير متوفرة حالياً."

        deposit_products = [p for p in products if p.requires_deposit and p.deposit_amount]
        if deposit_products:
            names = "، ".join(p.title for p in deposit_products)
            return (
                f"المنتج ({names}) محتاج ديبوزيت مقدماً مع صورة إثبات التحويل، "
                "وده مش متاح من هنا فى الشات. كمّل الأوردر من صفحة الدفع فى الموقع "
                "عشان ترفع صورة الإيصال، وإحنا هنتابع معاك أول ما يوصلنا."
            )

        with transaction.atomic():
            products_total = sum(p.final_price for p in products)
            shipping = Decimal(str(shipping_total or 0))
            total_price = products_total + shipping

            order = Order.objects.create(
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_governorate=governorate,
                customer_address=address,
                shipping_price=shipping,
                total_price=total_price,
                status="pending_review",
            )

            per_item_shipping = shipping / len(products) if products else Decimal("0")
            for p in products:
                OrderItem.objects.create(
                    order=order,
                    product=p,
                    quantity=1,
                    price_at_order_time=p.final_price,
                    shipping_price=per_item_shipping,
                    shipping_location=shipping_location or governorate,
                )

            commission_total = sum(p.commission_value for p in products)
            if commission_total > 0:
                Commission.objects.create(order=order, amount=commission_total)

            if conversation_id:
                try:
                    conv = ChatConversation.objects.get(id=conversation_id)
                    conv.last_message_at = order.created_at
                    conv.save(update_fields=["last_message_at"])
                except ChatConversation.DoesNotExist:
                    pass

        _send_order_telegram(order)

        return (
            f"تم تسجيل الأوردر بنجاح! رقم الأوردر: {order.order_number}\n"
            f"إجمالي المنتجات: {products_total} جنيه\n"
            f"الشحن: {shipping} جنيه\n"
            f"الإجمالي الكلي: {total_price} جنيه"
        )

    return await _create()


@tool
async def answer_general_policy(question_type: str) -> str:
    """يجيب على الأسئلة العامة: shipping أو payment أو returns."""
    policies = {
        "shipping": "مدة الشحن تتراوح بين 3 إلى 7 أيام عمل حسب المحافظة. تكلفة الشحن تعتمد على المحافظة والمنطقة.",
        "payment": "ندعم الدفع عند الاستلام. بعض المنتجات قد تتطلب ديبوزيت — يُؤكد من قاعدة البيانات فقط.",
        "returns": "يمكنك معاينة المنتج مع المندوب عند الاستلام. لا يمكن الاسترجاع بعد استلام المنتج.",
    }
    return policies.get(
        question_type,
        "السياسة غير متوفرة. صعّد للأدمن إذا لزم الأمر.",
    )

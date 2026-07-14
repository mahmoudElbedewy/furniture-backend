from agent.models import AgentActionRequest
from catalog.models import (
    Category,
    Product,
    ProductImage,
    ProductShippingRate,
    Governorate,
    Area,
)
from suppliers.models import Supplier
from django.utils.text import slugify
from django.db import transaction
import uuid
import requests
from django.core.files.base import ContentFile


def handle_agent_action_approval(request_id: str):
    try:
        req = AgentActionRequest.objects.get(id=request_id)
    except AgentActionRequest.DoesNotExist:
        return "❌ الطلب مش موجود."

    if req.status != "pending":
        return "⚠️ الطلب تم التعامل معه من قبل."
    if req.action_type != "add_product":
        return "❌ نوع الطلب غير مدعوم."

    payload = req.payload

    with transaction.atomic():
        supplier_name = payload.get("supplier_name")
        supplier, _ = Supplier.objects.get_or_create(
            channel_name=supplier_name or "إدارة الموقع (افتراضي)"
        )

        category_name = payload.get("category_name") or "عام"
        category, _ = Category.objects.get_or_create(
            name=category_name,
            defaults={
                "slug": slugify(category_name, allow_unicode=True)
                or f"cat-{uuid.uuid4().hex[:6]}"
            },
        )

        title = payload.get("title") or f"منتج {uuid.uuid4().hex[:6]}"
        slug = slugify(title, allow_unicode=True)
        if Product.objects.filter(slug=slug).exists():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        commission_value = payload.get("commission_value", 0)
        if isinstance(commission_value, str):
            try:
                commission_value = float(commission_value)
            except ValueError:
                commission_value = 0

        product = Product.objects.create(
            supplier=supplier,
            category=category,
            title=title,
            slug=slug,
            description=payload.get("description"),
            material=payload.get("material"),
            color=payload.get("color"),
            dimensions=payload.get("dimensions"),
            base_price=payload.get("base_price", 0),
            commission_value=commission_value,
            ships_nationwide=payload.get("ships_nationwide", True),
            default_shipping_price=payload.get("default_shipping_price"),
            requires_deposit=payload.get("requires_deposit", False),
            deposit_amount=payload.get("deposit_amount"),
            deposit_note=payload.get("deposit_note"),
        )

        for rate in payload.get("shipping_rates", []):
            gov_name, price = rate.get("governorate"), rate.get("price")
            if gov_name and price not in (None, ""):
                gov, _ = Governorate.objects.get_or_create(name=gov_name)
                area_obj = None
                if rate.get("area"):
                    area_obj, _ = Area.objects.get_or_create(
                        governorate=gov, name=rate["area"]
                    )
                ProductShippingRate.objects.create(
                    product=product, governorate=gov, area=area_obj, price=price
                )

        req.status = "approved"
        req.save()

    for img_data in payload.get("images", []):
        url = img_data.get("url")
        if not url:
            continue
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                ProductImage.objects.create(
                    product=product,
                    is_primary=img_data.get("is_primary", False),
                    image=ContentFile(resp.content, name=f"{uuid.uuid4().hex}.jpg"),
                )
        except requests.RequestException as e:
            print(f"Error downloading product image: {e}")

    return f"✅ تم إضافة المنتج: {product.title}"


def handle_agent_action_rejection(request_id: str):
    try:
        req = AgentActionRequest.objects.get(id=request_id)
    except AgentActionRequest.DoesNotExist:
        return "❌ الطلب مش موجود."
    if req.status != "pending":
        return "⚠️ الطلب تم التعامل معه من قبل."
    req.status = "rejected"
    req.save()
    return "❌ تم رفض الطلب ولن يتم إضافته."

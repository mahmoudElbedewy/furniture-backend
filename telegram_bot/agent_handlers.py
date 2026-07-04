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


@transaction.atomic
def handle_agent_action_approval(request_id: str):
    try:
        req = AgentActionRequest.objects.get(id=request_id)
    except AgentActionRequest.DoesNotExist:
        return "❌ الطلب مش موجود."

    if req.status != "pending":
        return "⚠️ الطلب تم التعامل معه من قبل."

    if req.action_type == "add_product":
        payload = req.payload

        # Debug logging
        print(f"DEBUG: Payload commission_value = {payload.get('commission_value')}")
        print(f"DEBUG: Full payload keys = {payload.keys()}")

        # 1. Supplier
        supplier_name = payload.get("supplier_name")
        supplier = None
        if supplier_name:
            supplier, _ = Supplier.objects.get_or_create(channel_name=supplier_name)
        else:
            supplier, _ = Supplier.objects.get_or_create(
                channel_name="إدارة الموقع (افتراضي)"
            )

        # 2. Category
        category_name = payload.get("category_name") or "عام"
        category, _ = Category.objects.get_or_create(
            name=category_name,
            defaults={
                "slug": slugify(category_name, allow_unicode=True)
                or f"cat-{uuid.uuid4().hex[:6]}"
            },
        )

        # 3. Product
        title = payload.get("title") or f"منتج {uuid.uuid4().hex[:6]}"
        slug = slugify(title, allow_unicode=True)
        # Ensure slug is unique
        if Product.objects.filter(slug=slug).exists():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        commission_value = payload.get("commission_value", 0)
        # Handle string to decimal conversion
        if isinstance(commission_value, str):
            try:
                commission_value = float(commission_value)
            except (ValueError, TypeError):
                commission_value = 0

        print(f"DEBUG: Final commission_value to save = {commission_value}")

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

        print(f"DEBUG: Saved product commission_value = {product.commission_value}")

        # 4. Images
        images = payload.get("images", [])
        # We might need to download images or just save the URL?
        # Actually ProductImage uses ImageField. We can't just pass a URL to ImageField easily without downloading.
        # But if the URLs are from our own Cloudinary or they are just placeholders, it's tricky.
        # Let's assume for now the images were uploaded and URLs are Cloudinary URLs or we have a way to store them.
        # This is a known limitation when moving from URL to ImageField. We'll skip image downloading here
        # and assume the admin will link them or we can add a URL field later if needed,
        # or download it directly using requests. Let's try downloading them and saving them.
        import requests
        from django.core.files.base import ContentFile

        for img_data in images:
            url = img_data.get("url")
            is_primary = img_data.get("is_primary", False)
            if url:
                try:
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        file_name = f"{uuid.uuid4().hex}.jpg"
                        ProductImage.objects.create(
                            product=product,
                            is_primary=is_primary,
                            image=ContentFile(resp.content, name=file_name),
                        )
                except Exception as e:
                    print("Error downloading image:", e)

        # 5. Shipping Rates
        rates = payload.get("shipping_rates", [])
        for rate in rates:
            gov_name = rate.get("governorate")
            price = rate.get("price")
            if gov_name and price not in (None, ""):
                gov, _ = Governorate.objects.get_or_create(name=gov_name)
                area_name = rate.get("area")
                area_obj = None
                if area_name:
                    area_obj, _ = Area.objects.get_or_create(
                        governorate=gov, name=area_name
                    )

                ProductShippingRate.objects.create(
                    product=product, governorate=gov, area=area_obj, price=price
                )

        req.status = "approved"
        req.save()
        return f"✅ تم إضافة المنتج: {product.title}"

    return "❌ نوع الطلب غير مدعوم."


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

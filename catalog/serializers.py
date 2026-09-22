from django.conf import settings
from rest_framework import serializers
from .models import (
    Category,
    Product,
    ProductImage,
    Review,
    ProductShippingRate,
    Favorite,
    ProductVariant,
)


def optimized_cloudinary_url(url, width=800):
    """Serve responsive Cloudinary derivatives without changing stored originals."""
    if not url or "/upload/" not in url or "res.cloudinary.com" not in url:
        return url
    return url.replace(
        "/upload/",
        f"/upload/f_auto,q_auto,w_{width},c_limit/",
        1,
    )


class CategorySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = "__all__"

    def get_image(self, obj):
        if obj.image:
            return obj.image.url
        return None


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ("id", "image", "is_primary")

    def get_image(self, obj):
        if obj.image:
            return obj.image.url
        return None


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = (
            "id",
            "customer_name",
            "rating",
            "comment",
            "is_verified_purchase",
            "created_at",
        )


class ProductShippingRateSerializer(serializers.ModelSerializer):
    governorate_name = serializers.CharField(source="governorate.name", read_only=True)
    area_name = serializers.CharField(
        source="area.name", read_only=True, allow_null=True
    )

    class Meta:
        model = ProductShippingRate
        fields = ("governorate_name", "area_name", "price")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    images = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()
    shipping_rates = serializers.SerializerMethodField()
    shipping_summary = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    measurement_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "material",
            "color",
            "color_options",
            "dimensions",
            "measurement_image",
            "final_price",
            "is_available",
            "category_name",
            "category_slug",
            "requires_deposit",
            "deposit_amount",
            "deposit_note",
            "default_shipping_price",
            "ships_nationwide",
            "images",
            "reviews",
            "shipping_rates",
            "shipping_summary",
            "variants",
        )

    def get_images(self, obj):
        # The main store view always starts at index 0, so keep the primary
        # image first even when it was uploaded after the other images.
        imgs = sorted(obj.images.all(), key=lambda image: not image.is_primary)
        return ProductImageSerializer(imgs, many=True).data

    def get_measurement_image(self, obj):
        if not obj.measurement_image:
            return None
        return obj.measurement_image.url

    def get_reviews(self, obj):
        revs = list(obj.reviews.all())[:5]
        return ReviewSerializer(revs, many=True).data

    def get_shipping_rates(self, obj):
        rates = obj.shipping_rates.all()
        return ProductShippingRateSerializer(rates, many=True).data

    def get_shipping_summary(self, obj):
        rates = obj.shipping_rates.all()
        estimated_delivery = getattr(
            settings,
            "STORE_DELIVERY_ESTIMATE",
            "خلال أسبوع من تأكيد الطلب",
        )
        if not rates:
            return {
                "free_shipping_areas": [],
                "paid_shipping_areas": [],
                "has_free_shipping": obj.default_shipping_price == 0,
                "default_price": (
                    float(obj.default_shipping_price)
                    if obj.default_shipping_price
                    else None
                ),
                "message": (
                    "شحن مجاني لجميع المحافظات"
                    if obj.default_shipping_price == 0
                    else "يوجد رسوم شحن"
                ),
                "estimated_delivery": estimated_delivery,
            }

        free_areas = []
        paid_areas = {}
        for rate in rates:
            location = f"{rate.governorate.name}"
            if rate.area:
                location += f" - {rate.area.name}"
            if rate.price == 0:
                free_areas.append(location)
            else:
                paid_areas.setdefault(rate.price, []).append(location)

        paid_shipping_list = [
            {"price": float(price), "areas": areas, "count": len(areas)}
            for price, areas in sorted(paid_areas.items())
        ]

        return {
            "free_shipping_areas": free_areas,
            "paid_shipping_areas": paid_shipping_list,
            "has_free_shipping": len(free_areas) > 0,
            "default_price": (
                float(obj.default_shipping_price)
                if obj.default_shipping_price
                else None
            ),
            "estimated_delivery": estimated_delivery,
            "message": self._generate_shipping_message(
                free_areas, paid_shipping_list, obj.default_shipping_price
            ),
        }

    def _generate_shipping_message(self, free_areas, paid_areas, default_price):
        messages = []
        if free_areas:
            if len(free_areas) <= 3:
                messages.append(f"شحن مجاني لـ: {', '.join(free_areas)}")
            else:
                messages.append(f"شحن مجاني لـ {len(free_areas)} منطقة")
        if paid_areas:
            for item in paid_areas:
                areas_text = (
                    ", ".join(item["areas"])
                    if item["count"] <= 3
                    else f"{item['count']} منطقة"
                )
                messages.append(f"شحن {item['price']} جنيه لـ: {areas_text}")
        if default_price and default_price > 0:
            messages.append(f"السعر الافتراضي للشحن: {default_price} جنيه")
        return " | ".join(messages) if messages else "تواصل معنا لمعرفة تفاصيل الشحن"

    def get_variants(self, obj):
        variants = [v for v in obj.variants.all() if v.is_available]
        return ProductVariantSerializer(variants, many=True).data


class ProductCardSerializer(serializers.ModelSerializer):
    """Compact catalog payload; full product data is fetched on the PDP only."""

    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    images = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "title",
            "slug",
            "final_price",
            "is_available",
            "category_name",
            "category_slug",
            "material",
            "color",
            "images",
        )

    def get_images(self, obj):
        images = list(obj.images.all())
        image = next((item for item in images if item.is_primary), images[0] if images else None)
        if not image or not image.image:
            return []
        return [
            {
                "id": image.id,
                "image": optimized_cloudinary_url(image.image.url, width=720),
                "is_primary": True,
            }
        ]


class FavoriteSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    product_final_price = serializers.DecimalField(
        source="product.final_price", read_only=True, max_digits=10, decimal_places=2
    )

    class Meta:
        model = Favorite
        fields = (
            "id",
            "product",
            "product_title",
            "product_slug",
            "product_final_price",
            "customer_identifier",
            "created_at",
        )
        read_only_fields = ("created_at",)


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "size_name", "price", "is_available")

from rest_framework import serializers
from .models import Order, OrderItem
from catalog.models import Product


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_available=True), source="product"
    )
    product_title = serializers.CharField(source="product.title", read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "product_id",
            "product_title",
            "quantity",
            "price_at_order_time",
            "shipping_price",
            "shipping_location",
        )
        read_only_fields = ("price_at_order_time",)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    commission = serializers.SerializerMethodField()
    deposit_proof_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "customer_name",
            "customer_phone",
            "customer_governorate",
            "customer_address",
            "status",
            "shipping_price",
            "total_price",
            "notes",
            "created_at",
            "items",
            "commission",
            "deposit_proof_image",
            "deposit_amount",
        )
        read_only_fields = ("order_number", "total_price", "deposit_amount")

    def validate(self, attrs):
        items = attrs.get("items", [])
        total_deposit = sum(
            (item["product"].deposit_amount or 0) * item.get("quantity", 1)
            for item in items
            if getattr(item["product"], "requires_deposit", False)
        )
        if total_deposit > 0 and not attrs.get("deposit_proof_image"):
            raise serializers.ValidationError(
                {"deposit_proof_image": "يجب رفع صورة إيصال الديبوزيت لهذا الطلب."}
            )
        attrs["_total_deposit"] = total_deposit
        return attrs

    def get_commission(self, obj):
        commission = getattr(obj, "commission", None)
        if not commission:
            return None
        return {
            "id": str(commission.id),
            "amount": commission.amount,
            "is_settled": commission.is_settled,
            "settled_at": commission.settled_at,
        }

    def update(self, instance, validated_data):
        status = validated_data.get("status", instance.status)
        old_status = instance.status

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if status != old_status:
            from django.utils import timezone

            commission = getattr(instance, "commission", None)

            if status == "commission_settled" and commission:
                commission.is_settled = True
                commission.settled_at = timezone.now()
                commission.save()
            elif old_status == "commission_settled" and commission:
                commission.is_settled = False
                commission.settled_at = None
                commission.save()

        return instance

    def create(self, validated_data):
        try:
            total_deposit = validated_data.pop("_total_deposit", 0)
            items_data = validated_data.pop("items")

            shipping_price = validated_data.pop("shipping_price", 0)
            # Convert to Decimal if needed
            if shipping_price is not None:
                from decimal import Decimal

                if not isinstance(shipping_price, Decimal):
                    shipping_price = Decimal(str(shipping_price))

            total = (
                sum(
                    [
                        item["product"].final_price * item.get("quantity", 1)
                        for item in items_data
                    ]
                )
                + shipping_price
            )

            order = Order.objects.create(
                total_price=total,
                shipping_price=shipping_price,
                deposit_amount=total_deposit,
                **validated_data,
            )

            request = self.context.get("request")
            if request and request.user.is_authenticated:
                order.user = request.user
                order.save()

            for item_data in items_data:
                OrderItem.objects.create(
                    order=order,
                    product=item_data["product"],
                    quantity=item_data.get("quantity", 1),
                    price_at_order_time=item_data["product"].final_price,
                    shipping_price=item_data.get("shipping_price", 0),
                    shipping_location=item_data.get("shipping_location", ""),
                )

            # Send Telegram notification after items are created
            self._send_telegram_notification(order)

            return order
        except Exception as e:
            import traceback

            print(f"Error creating order: {e}")
            print(traceback.format_exc())
            raise

    def _send_telegram_notification(self, order):
        """Send Telegram notification with order details"""
        try:
            from telegram_bot.services import notify_admin

            from html import escape

            lines = []
            for item in order.items.all():
                product = item.product
                base = product.base_price
                commission = product.commission_value
                after_commission = item.price_at_order_time
                description = escape(product.description or "لا يوجد وصف")
                item_shipping = item.shipping_price or 0
                item_location = escape(item.shipping_location or "غير محدد")
                lines.append(
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📦 <b>{product.title}</b> x{item.quantity}\n"
                    f"📝 الوصف: {description}\n"
                    f"💰 السعر قبل العمولة: {base} ج\n"
                    f"💵 العمولة: {commission} ج\n"
                    f"💲 السعر بعد العمولة: {after_commission} ج\n"
                    f"🚚 الشحن: {item_shipping} ج\n"
                    f"📍 مكان الشحن: {item_location}"
                )

            items_text = "\n\n".join(lines) or "لا توجد عناصر بعد"

            message = (
                f"🛒 <b>أوردر جديد</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🆔 رقم الأوردر: {order.order_number}\n"
                f"👤 العميل: {escape(order.customer_name)}\n"
                f"📱 رقم الهاتف: {escape(order.customer_phone)}\n"
                f"📍 المحافظة: {escape(order.customer_governorate)}"
                + (f" - {escape(order.customer_area)}" if order.customer_area else "")
                + "\n"
                f"🏠 العنوان: {escape(order.customer_address)}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📦 المنتجات:\n\n{items_text}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🚚 تكلفة الشحن: {order.shipping_price} ج\n"
                f"💵 الإجمالي: {order.total_price} ج"
            )
            buttons = [
                {
                    "text": "✅ موافقة",
                    "callback_data": f"order_approve:{order.order_number}",
                },
                {
                    "text": "❌ رفض",
                    "callback_data": f"order_reject:{order.order_number}",
                },
            ]

            notify_admin("new_order", order.id, message, buttons=buttons)
        except Exception as e:
            # Log error but don't fail the order creation
            print(f"Failed to send Telegram notification: {e}")

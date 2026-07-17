import uuid
from django.db import models
from django.conf import settings
from catalog.models import Product


class Order(models.Model):
    STATUS_CHOICES = (
        ("pending_review", "قيد المراجعة"),
        ("supplier_confirmed", "تم التأكيد"),
        ("out_for_delivery", "جاري التوصيل"),
        ("delivered", "تم التسليم"),
        ("commission_settled", "تمت تسوية العمولة"),
        ("cancelled", "ملغي"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=20, unique=True, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=20)
    customer_governorate = models.CharField(max_length=100)
    customer_area = models.CharField(max_length=100, blank=True, null=True)
    customer_address = models.TextField()

    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default="pending_review"
    )
    shipping_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposit_proof_image = models.ImageField(
        upload_to="deposit_proofs/", blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
    )  
    variant_size_name = models.CharField(max_length=100, blank=True, null=True)  # نسخة نصية ثابتة وقت الطلب
    quantity = models.PositiveIntegerField(default=1)
    price_at_order_time = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_location = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        size = f" ({self.variant_size_name})" if self.variant_size_name else ""
        return f"{self.order.order_number} - {self.product.title}{size} x{self.quantity}"


class OrderStatusLog(models.Model):
    CHANGED_BY_CHOICES = (
        ("admin", "Admin"),
        ("agent", "Agent"),
        ("system", "System"),
    )

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="status_logs"
    )
    old_status = models.CharField(max_length=25, blank=True, null=True)
    new_status = models.CharField(max_length=25)
    changed_by = models.CharField(
        max_length=10, choices=CHANGED_BY_CHOICES, default="system"
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order.order_number}: {self.old_status} → {self.new_status}"


class Commission(models.Model):
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="commission"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_settled = models.BooleanField(default=False)
    settled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.order.order_number} - {self.amount} ({'تمت التسوية' if self.is_settled else 'معلقة'})"


class AbandonedCart(models.Model):
    phone_number = models.CharField(max_length=20)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    captured_at = models.DateTimeField(auto_now_add=True)
    converted_to_order = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.phone_number} - {self.product.title}"

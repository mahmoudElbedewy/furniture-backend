import uuid
from django.db import models
from suppliers.models import Supplier

def category_image_upload_path(instance, filename):
    ext = filename.split(".")[-1]
    return f"categories/{uuid.uuid4().hex}.{ext}"


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    image = models.ImageField(
        upload_to=category_image_upload_path, blank=True, null=True
    )

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Governorate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    region = models.CharField(
        max_length=50, blank=True, null=True
    )  # دلتا / صعيد / وجه بحري

    def __str__(self):
        return self.name


class Area(models.Model):
    governorate = models.ForeignKey(
        Governorate, on_delete=models.CASCADE, related_name="areas"
    )
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.governorate.name} - {self.name}"


class Product(models.Model):
    COMMISSION_TYPE_CHOICES = (
        ("fixed", "Fixed"),
        ("percentage", "Percentage"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.PROTECT, related_name="products"
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True, null=True)
    material = models.CharField(max_length=100, blank=True, null=True)
    color = models.CharField(max_length=200, blank=True, null=True)
    dimensions = models.CharField(
        max_length=150, blank=True, null=True
    )  # "عرض 175 × ارتفاع 31"

    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    commission_value = models.DecimalField(max_digits=10, decimal_places=2)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    ships_nationwide = models.BooleanField(default=True)
    default_shipping_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    requires_deposit = models.BooleanField(default=False)
    deposit_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    deposit_note = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="ملاحظة عن الديبوزيت، مثلاً: يتم دفعه عند التأكيد",
    )

    is_available = models.BooleanField(default=True)
    views_count = models.PositiveIntegerField(default=0)
    orders_count = models.PositiveIntegerField(default=0)

    source_raw_text = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.final_price = self.base_price + self.commission_value
        super().save(*args, **kwargs)

    def primary_image_url(self):
        img = self.images.filter(is_primary=True).first() or self.images.first()
        return img.image.url if img and img.image else None

    def __str__(self):
        return self.title


def product_image_upload_path(instance, filename):
    ext = filename.split(".")[-1]
    return f"products/{uuid.uuid4().hex}.{ext}"


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=product_image_upload_path)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product.title} - Image"


class ProductShippingRate(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="shipping_rates"
    )
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE)
    area = models.ForeignKey(Area, on_delete=models.CASCADE, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ("product", "governorate", "area")

    def __str__(self):
        location = f"{self.governorate.name}" + (
            f" - {self.area.name}" if self.area else ""
        )
        return f"{self.product.title} → {location}: {self.price}"


class Review(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    customer_name = models.CharField(max_length=150)
    rating = models.PositiveSmallIntegerField()  # 1-5
    comment = models.TextField(blank=True, null=True)
    is_verified_purchase = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.title} - {self.rating}★"


class Favorite(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="favorites"
    )
    customer_identifier = models.CharField(max_length=255)  # session_id or user email
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product", "customer_identifier")
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"

    def __str__(self):
        return f"{self.product.title} - {self.customer_identifier}"
class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )
    size_name = models.CharField(max_length=100)  
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.product.title} - {self.size_name}: {self.price}"
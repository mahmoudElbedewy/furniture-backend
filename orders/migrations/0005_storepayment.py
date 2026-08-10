import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_orderitem_variant"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorePayment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "payment_type",
                    models.CharField(
                        choices=[
                            ("ads", "Ads"),
                            ("shipping", "Shipping"),
                            ("tools", "Tools"),
                            ("other", "Other"),
                        ],
                        default="ads",
                        max_length=30,
                    ),
                ),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                ("paid_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-paid_at", "-created_at"],
            },
        ),
    ]

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0005_productvariant"),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchQuery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query", models.CharField(max_length=255)),
                ("normalized_query", models.CharField(db_index=True, max_length=255)),
                ("results_count", models.PositiveIntegerField(default=0)),
                ("has_results", models.BooleanField(db_index=True, default=False)),
                ("customer_identifier", models.CharField(blank=True, default="", max_length=255)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="search_queries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "search_queries",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["normalized_query", "created_at"], name="search_quer_normali_4a920c_idx"),
                    models.Index(fields=["has_results", "created_at"], name="search_quer_has_res_2fb51f_idx"),
                ],
            },
        ),
    ]

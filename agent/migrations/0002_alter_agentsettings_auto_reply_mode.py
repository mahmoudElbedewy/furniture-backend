from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agentsettings",
            name="auto_reply_mode",
            field=models.CharField(
                choices=[
                    ("full_auto", "رد تلقائي كامل"),
                    ("suggest_only", "اقتراح فقط"),
                    ("off", "إيقاف تام"),
                ],
                default="full_auto",
                max_length=15,
            ),
        ),
    ]

# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="escalation_note",
            field=models.TextField(blank=True, default=""),
        ),
    ]

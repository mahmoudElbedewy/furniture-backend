from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0002_chatconversation_escalation_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="force_agent_auto",
            field=models.BooleanField(default=False),
        ),
    ]

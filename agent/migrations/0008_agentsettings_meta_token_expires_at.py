from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0007_remove_analytics_seed_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentsettings',
            name='meta_token_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
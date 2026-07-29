from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0008_agentsettings_meta_token_expires_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='SyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(choices=[('facebook', 'Facebook'), ('ga4', 'Google Analytics 4')], max_length=20)),
                ('status', models.CharField(choices=[('success', 'نجاح'), ('failure', 'فشل')], max_length=10)),
                ('message', models.TextField(blank=True, default='')),
                ('started_at', models.DateTimeField()),
                ('finished_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-finished_at'],
                'indexes': [models.Index(fields=['source', 'finished_at'], name='agent_syncl_source_fin_idx')],
            },
        ),
    ]
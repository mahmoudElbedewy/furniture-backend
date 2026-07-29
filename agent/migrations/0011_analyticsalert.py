from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0010_funnelevent'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnalyticsAlert',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alert_type', models.CharField(
                    choices=[
                        ('sessions_drop', 'انخفاض الجلسات'),
                        ('bounce_rate_spike', 'ارتفاع معدل الارتداد'),
                        ('meta_sync_stopped', 'توقف مزامنة Meta'),
                        ('ga4_sync_stopped', 'توقف مزامنة GA4'),
                        ('meta_token_expiring', 'توكن Meta على وشك الانتهاء'),
                        ('orders_drop', 'انخفاض الطلبات'),
                        ('no_data', 'لا توجد بيانات'),
                    ],
                    db_index=True,
                    max_length=30,
                )),
                ('severity', models.CharField(
                    choices=[
                        ('info', 'معلومة'),
                        ('warning', 'تحذير'),
                        ('critical', 'حرج'),
                    ],
                    default='info',
                    max_length=10,
                )),
                ('message', models.TextField()),
                ('detail', models.TextField(blank=True, default='')),
                ('is_read', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('threshold_pct', models.FloatField(blank=True, null=True)),
                ('actual_value', models.FloatField(blank=True, null=True)),
                ('previous_value', models.FloatField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='analyticsalert',
            index=models.Index(fields=['is_read', 'created_at'], name='agent_analy_is_read_idx'),
        ),
        migrations.AddIndex(
            model_name='analyticsalert',
            index=models.Index(fields=['alert_type', 'created_at'], name='agent_analy_type_idx'),
        ),
    ]

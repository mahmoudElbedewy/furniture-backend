import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0009_synclog'),
        ('catalog', '0005_productvariant'),
        ('orders', '0004_orderitem_variant'),
    ]

    operations = [
        migrations.CreateModel(
            name='FunnelEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('product_view', 'مشاهدة منتج'), ('add_to_cart', 'إضافة للسلة'), ('checkout_start', 'بدء الدفع'), ('order_complete', 'إتمام الطلب')], db_index=True, max_length=20)),
                ('session_key', models.CharField(blank=True, default='', max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='funnel_events', to='orders.order')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='funnel_events', to='catalog.product')),
            ],
            options={
                'indexes': [models.Index(fields=['event_type', 'created_at'], name='agent_funne_event_t_idx')],
            },
        ),
    ]
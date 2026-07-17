import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0003_order_deposit_amount_order_deposit_proof_image'),
        ('catalog', '0005_productvariant'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='variant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='order_items', to='catalog.productvariant'),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='variant_size_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
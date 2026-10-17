from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0039_purchase_bank_payment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchasedetail',
            name='price',
            field=models.DecimalField(decimal_places=6, default=0.0, max_digits=14),
        ),
    ]

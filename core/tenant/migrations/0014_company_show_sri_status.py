from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenant', '0013_sriruc'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='show_sri_status',
            field=models.BooleanField(default=False, verbose_name='Mostrar el estado del contribuyente en el SRI al consultar un RUC o cédula'),
        ),
    ]

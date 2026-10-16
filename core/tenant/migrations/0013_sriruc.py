from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenant', '0012_company_keep_accounting_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='SriRuc',
            fields=[
                ('ruc', models.CharField(max_length=13, primary_key=True, serialize=False, verbose_name='RUC')),
                ('business_name', models.CharField(max_length=300, verbose_name='Razón social')),
                ('trade_name', models.CharField(blank=True, max_length=300, null=True, verbose_name='Nombre comercial')),
                ('status', models.CharField(max_length=30, verbose_name='Estado del contribuyente')),
                ('taxpayer_type', models.CharField(blank=True, max_length=30, null=True, verbose_name='Tipo de contribuyente')),
                ('accounting_required', models.BooleanField(default=False, verbose_name='Obligado a llevar contabilidad')),
                ('province', models.CharField(blank=True, max_length=60, null=True, verbose_name='Provincia')),
                ('canton', models.CharField(blank=True, max_length=60, null=True, verbose_name='Cantón')),
                ('catalog_date', models.DateField(verbose_name='Fecha de los datos')),
            ],
            options={
                'verbose_name': 'RUC del catálogo SRI',
                'verbose_name_plural': 'RUC del catálogo SRI',
            },
        ),
    ]

from django.db import migrations, connection
from django_tenants.utils import get_public_schema_name


def create_quotation_receipt(apps, schema_editor):
    if connection.schema_name == get_public_schema_name():
        return
    Receipt = apps.get_model('pos', 'Receipt')
    Company = apps.get_model('tenant', 'Company')
    company = Company.objects.filter(scheme__schema_name=connection.schema_name).first()
    if company is None:
        return
    Receipt.objects.get_or_create(
        voucher_type='COT',
        establishment_code=company.establishment_code,
        issuing_point_code=company.issuing_point_code,
        defaults={'sequence': 1},
    )


def remove_quotation_receipt(apps, schema_editor):
    if connection.schema_name == get_public_schema_name():
        return
    Receipt = apps.get_model('pos', 'Receipt')
    Receipt.objects.filter(voucher_type='COT', quotation__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0003_quotation_receipt_quotation_voucher_number_and_more'),
        ('tenant', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_quotation_receipt, remove_quotation_receipt),
    ]

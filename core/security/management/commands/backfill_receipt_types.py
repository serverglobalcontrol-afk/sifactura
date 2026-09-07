from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company
from core.pos.choices import VOUCHER_TYPE


class Command(BaseCommand):
    help = (
        "Crea, en cada compañía existente, los comprobantes (Receipt) para "
        "cualquier tipo de VOUCHER_TYPE que aún no tenga - por ejemplo "
        "LIQUIDACIÓN DE COMPRA, agregado después de que las compañías ya "
        "existían. create_base_modules() solo crea un Receipt por tipo al "
        "crear la compañía, así que un tipo de comprobante agregado después "
        "queda faltando en las compañías anteriores (no aparece en el "
        "listado de Comprobantes aunque la compañía lo tenga habilitado). "
        "Seguro de volver a ejecutar."
    )

    def handle(self, *args, **options):
        from core.pos.models import Receipt

        with schema_context('public'):
            companies = list(Company.objects.all())

        for company in companies:
            with schema_context(company.schema_name):
                created = 0
                for code, label in VOUCHER_TYPE:
                    receipt, was_created = Receipt.objects.get_or_create(
                        voucher_type=code,
                        establishment_code=company.establishment_code,
                        issuing_point_code=company.issuing_point_code,
                        defaults={'sequence': 0},
                    )
                    if was_created:
                        created += 1
                        self.stdout.write(f'{company.business_name}: comprobante {label!r} creado')

                if not created:
                    self.stdout.write(f'{company.business_name} ({company.schema_name}): ya estaba al día')

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

MODULE_URL = '/pos/quotation/'
GROUP_NAME = 'Punto de Venta'


class Command(BaseCommand):
    help = (
        "Da acceso al módulo de Cotizaciones (crear, ver, editar, eliminar, "
        "imprimir y convertir a factura) al grupo 'Punto de Venta' en las "
        "compañías que ya existían antes de este cambio, ya que "
        "create_base_modules() solo se ejecuta al crear una compañía nueva. "
        "Es seguro volver a ejecutarlo: si el grupo ya tiene el módulo, se omite."
    )

    def handle(self, *args, **options):
        from core.security.models import Module, Group, GroupModule

        with schema_context('public'):
            companies = list(Company.objects.filter(active=True))

        for company in companies:
            with schema_context(company.schema_name):
                module = Module.objects.filter(url=MODULE_URL).first()
                group = Group.objects.filter(name=GROUP_NAME).first()
                if not module:
                    self.stdout.write(self.style.WARNING(f'{company.business_name}: no existe el módulo de Cotizaciones, se omite'))
                    continue
                if not group:
                    self.stdout.write(self.style.WARNING(f"{company.business_name}: no existe el grupo '{GROUP_NAME}', se omite"))
                    continue
                if GroupModule.objects.filter(module=module, group=group).exists():
                    self.stdout.write(f'{company.business_name}: el grupo ya tenía el módulo, se omite')
                    continue
                GroupModule.objects.create(module=module, group=group)
                for permission in module.permissions.all():
                    group.permissions.add(permission)
                self.stdout.write(self.style.SUCCESS(f'{company.business_name}: acceso a Cotizaciones agregado al grupo {group.name}'))

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

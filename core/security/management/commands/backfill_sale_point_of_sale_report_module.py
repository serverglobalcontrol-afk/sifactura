from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

MODULE_URL = '/reports/sale/point-of-sale/'
MODULE_NAME = 'Ventas por Punto de Venta'
MODULE_ICON = 'fas fa-cash-register'
MODULE_DESCRIPTION = 'Permite ver las ventas diarias de cada punto de venta, en general o filtrado por fechas y por punto de venta puntual'
MODULE_TYPE_NAME = 'Reportes'


class Command(BaseCommand):
    help = (
        "Agrega el módulo 'Ventas por Punto de Venta' (y su acceso para el grupo "
        "Administrador) a las compañías que ya existían antes de que se creara este "
        "reporte, ya que create_base_modules() solo se ejecuta al crear una compañía "
        "nueva. Es seguro volver a ejecutarlo: si el módulo ya existe en una compañía, "
        "se omite."
    )

    def handle(self, *args, **options):
        from core.security.models import Module, ModuleType, Group, GroupModule

        with schema_context('public'):
            companies = list(Company.objects.filter(active=True))

        for company in companies:
            with schema_context(company.schema_name):
                if Module.objects.filter(url=MODULE_URL).exists():
                    self.stdout.write(f'{company.business_name}: el módulo ya existe, se omite')
                    continue
                module_type = ModuleType.objects.filter(name=MODULE_TYPE_NAME).first()
                module = Module.objects.create(
                    url=MODULE_URL,
                    name=MODULE_NAME,
                    module_type=module_type,
                    description=MODULE_DESCRIPTION,
                    icon=MODULE_ICON,
                )
                group = Group.objects.filter(name='Administrador').first()
                if group:
                    GroupModule.objects.create(module=module, group=group)
                    self.stdout.write(self.style.SUCCESS(f'{company.business_name}: módulo agregado y asignado a {group.name}'))
                else:
                    self.stdout.write(self.style.WARNING(f'{company.business_name}: módulo agregado, pero no se encontró el grupo Administrador'))

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

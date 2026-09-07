from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

MODULE_TYPE_NAME = 'Reportes'

NEW_MODULES = [
    {
        'url': '/reports/product/low-stock/',
        'name': 'Productos con Stock Bajo',
        'icon': 'fas fa-exclamation-triangle',
        'description': 'Permite ver los productos inventariados cuyo stock llegó al mínimo configurado o está en negativo',
    },
    {
        'url': '/reports/product/best-sellers/',
        'name': 'Productos Más Vendidos',
        'icon': 'fas fa-trophy',
        'description': 'Permite ver los productos más vendidos en un rango de fechas',
    },
]


class Command(BaseCommand):
    help = (
        "Agrega los módulos 'Productos con Stock Bajo' y 'Productos Más Vendidos' (y "
        "su acceso para el grupo Administrador) a las compañías que ya existían antes "
        "de que se crearan estos reportes, ya que create_base_modules() solo se "
        "ejecuta al crear una compañía nueva. Es seguro volver a ejecutarlo: si un "
        "módulo ya existe en una compañía, se omite."
    )

    def handle(self, *args, **options):
        from core.security.models import Module, ModuleType, Group, GroupModule

        with schema_context('public'):
            companies = list(Company.objects.filter(active=True))

        for company in companies:
            with schema_context(company.schema_name):
                module_type = ModuleType.objects.filter(name=MODULE_TYPE_NAME).first()
                group = Group.objects.filter(name='Administrador').first()
                for module_data in NEW_MODULES:
                    if Module.objects.filter(url=module_data['url']).exists():
                        self.stdout.write(f"{company.business_name}: {module_data['name']} ya existe, se omite")
                        continue
                    module = Module.objects.create(
                        url=module_data['url'],
                        name=module_data['name'],
                        module_type=module_type,
                        description=module_data['description'],
                        icon=module_data['icon'],
                    )
                    if group:
                        GroupModule.objects.create(module=module, group=group)
                        self.stdout.write(self.style.SUCCESS(f"{company.business_name}: {module.name} agregado y asignado a {group.name}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"{company.business_name}: {module.name} agregado, pero no se encontró el grupo Administrador"))

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

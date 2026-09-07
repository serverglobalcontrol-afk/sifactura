from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

MODULE_URL = '/pos/quotation/'
GROUP_NAMES = ['Administrador', 'Punto de Venta']


class Command(BaseCommand):
    help = (
        "Crea el módulo de Cotizaciones (si no existe) y lo asigna a los "
        "grupos 'Administrador' y 'Punto de Venta' en todas las compañías. "
        "El comando anterior (backfill_point_of_sale_quotation_access) solo "
        "cubría 'Punto de Venta' y se saltaba la compañía por completo si el "
        "módulo no existía, dejando 3 de 4 empresas activas sin acceso real "
        "a Cotizaciones (ni siquiera el grupo Administrador la tenía). "
        "Seguro de volver a ejecutar."
    )

    def handle(self, *args, **options):
        from django.contrib.auth.models import Permission
        from core.security.models import Module, Group, GroupModule, ModuleType

        with schema_context('public'):
            companies = list(Company.objects.all())

        for company in companies:
            with schema_context(company.schema_name):
                permissions = list(Permission.objects.filter(content_type__app_label='pos', content_type__model='quotation'))
                if not permissions:
                    self.stdout.write(self.style.WARNING(f'{company.business_name}: no existen los permisos de Cotización, se omite'))
                    continue

                moduletype = ModuleType.objects.filter(name='Facturación').first()
                module, created = Module.objects.get_or_create(
                    url=MODULE_URL,
                    defaults={
                        'name': 'Cotizaciones',
                        'module_type': moduletype,
                        'description': 'Permite administrar las cotizaciones de los productos',
                        'icon': 'fa-solid fa-file-lines',
                    },
                )
                if created:
                    for permission in permissions:
                        module.permissions.add(permission)
                    self.stdout.write(f"{company.business_name}: módulo 'Cotizaciones' creado")
                elif module.permissions.count() == 0:
                    for permission in permissions:
                        module.permissions.add(permission)
                    self.stdout.write(f"{company.business_name}: permisos agregados al módulo existente 'Cotizaciones'")

                for group_name in GROUP_NAMES:
                    group = Group.objects.filter(name=group_name).first()
                    if not group:
                        continue
                    if not GroupModule.objects.filter(module=module, group=group).exists():
                        GroupModule.objects.create(module=module, group=group)
                        for permission in permissions:
                            group.permissions.add(permission)
                        self.stdout.write(self.style.SUCCESS(f"{company.business_name}: acceso a 'Cotizaciones' agregado al grupo {group.name}"))
                    elif not group.permissions.filter(codename__in=[p.codename for p in permissions]).exists():
                        for permission in permissions:
                            group.permissions.add(permission)
                        self.stdout.write(self.style.SUCCESS(f"{company.business_name}: permisos de 'Cotizaciones' agregados al grupo {group.name} (ya tenía el módulo)"))

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

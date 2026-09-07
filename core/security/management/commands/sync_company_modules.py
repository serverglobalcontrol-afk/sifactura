from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

EMPLOYEE_URLS = ['/rrhh/employee/update/profile/', '/rrhh/assistance/employee/', '/rrhh/salary/employee/']
CLIENT_URLS = ['/pos/client/update/profile/', '/pos/sale/client/', '/pos/credit/note/client/']
POINT_OF_SALE_URLS = ['/pos/sale/admin/', '/pos/client/', '/pos/ctas/collect/', '/pos/debts/pay/', '/pos/quotation/']

# group_name -> (module urls it gets; None means "todos los módulos navegables
# excepto los del portal de cliente y de empleado", igual que create_base_modules)
GROUP_URLS = {
    'Administrador': None,
    'Cliente': CLIENT_URLS + ['/user/update/password/'],
    'Empleado': EMPLOYEE_URLS + ['/user/update/password/'],
    'Punto de Venta': POINT_OF_SALE_URLS + ['/user/update/password/'],
}


class Command(BaseCommand):
    help = (
        "Sincroniza TODOS los módulos base (los definidos en "
        "Company.get_base_modules_data) y los 4 grupos estándar "
        "(Administrador, Cliente, Empleado, Punto de Venta) en TODAS las "
        "compañías existentes, para que queden igual que una compañía creada "
        "hoy. create_base_modules() solo corre una vez, al crear la "
        "compañía, así que cualquier módulo o grupo agregado después queda "
        "faltando en las compañías ya existentes. Este comando: (1) crea los "
        "módulos que falten, (2) crea los grupos que falten, (3) asigna a "
        "cada grupo los módulos y permisos que le corresponden según las "
        "mismas reglas de create_base_modules(). Seguro de volver a "
        "ejecutar, no duplica ni borra nada existente."
    )

    def handle(self, *args, **options):
        from core.security.models import Module, Group, GroupModule, GroupSettings

        with schema_context('public'):
            companies = list(Company.objects.all())

        for company in companies:
            with schema_context(company.schema_name):
                canonical = company.get_base_modules_data()

                created_modules = 0
                for module_data in canonical:
                    module, created = Module.objects.get_or_create(
                        url=module_data['url'],
                        defaults={
                            'name': module_data['name'],
                            'module_type': module_data['moduletype'],
                            'description': module_data['description'],
                            'icon': module_data['icon'],
                        },
                    )
                    if created:
                        created_modules += 1
                        if module_data['permissions']:
                            for permission in module_data['permissions']:
                                module.permissions.add(permission)
                    elif module.permissions.count() == 0 and module_data['permissions']:
                        for permission in module_data['permissions']:
                            module.permissions.add(permission)

                created_groups = 0
                linked_modules = 0
                for group_name, urls in GROUP_URLS.items():
                    group, created = Group.objects.get_or_create(name=group_name)
                    if created:
                        created_groups += 1
                        if group_name == 'Punto de Venta':
                            GroupSettings.objects.get_or_create(group=group, defaults={'requires_cash_register': True})

                    if urls is None:
                        queryset = Module.objects.exclude(url__in=CLIENT_URLS + EMPLOYEE_URLS)
                    else:
                        queryset = Module.objects.filter(url__in=urls)

                    for module in queryset:
                        if not GroupModule.objects.filter(module=module, group=group).exists():
                            GroupModule.objects.create(module=module, group=group)
                            linked_modules += 1
                        for permission in module.permissions.all():
                            group.permissions.add(permission)

                if created_modules or created_groups or linked_modules:
                    self.stdout.write(self.style.SUCCESS(
                        f'{company.business_name} ({company.schema_name}): '
                        f'{created_modules} módulos creados, {created_groups} grupos creados, '
                        f'{linked_modules} asignaciones de módulo agregadas'
                    ))
                else:
                    self.stdout.write(f'{company.business_name} ({company.schema_name}): ya estaba al día')

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company

EMPLOYEE_URLS = ['/rrhh/employee/update/profile/', '/rrhh/assistance/employee/', '/rrhh/salary/employee/']
CLIENT_URLS = ['/pos/client/update/profile/', '/pos/sale/client/', '/pos/credit/note/client/']
POINT_OF_SALE_URLS = ['/pos/sale/admin/', '/pos/client/', '/pos/ctas/collect/', '/pos/debts/pay/', '/pos/quotation/', '/pos/expenses/', '/pos/purchase/']
# Borrar Cuentas por cobrar/pagar, Compras o Gastos queda reservado al
# perfil Administrador -Punto de Venta puede ver, crear y editar esos
# módulos, pero no eliminar sus registros.
POINT_OF_SALE_NO_DELETE_CODENAMES = ['delete_ctas_collect', 'delete_debts_pay', 'delete_purchase', 'delete_expenses']

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
        "mismas reglas de create_base_modules(), y (4) revoca al grupo "
        "'Punto de Venta' los permisos de borrado de Cuentas por cobrar/pagar, "
        "Compras y Gastos (reservados a Administrador). Seguro de volver a "
        "ejecutar, no duplica módulos ni permisos existentes -lo único que "
        "borra son esos permisos de borrado puntuales del grupo Punto de Venta."
    )

    def handle(self, *args, **options):
        from core.security.models import Module, Group, GroupModule, GroupSettings

        with schema_context('public'):
            companies = list(Company.objects.all())

        for company in companies:
            with schema_context(company.schema_name):
                canonical = company.get_base_modules_data()

                created_modules = 0
                reordered_modules = 0
                moved_modules = 0
                for module_data in canonical:
                    order = module_data.get('order', 0)
                    module, created = Module.objects.get_or_create(
                        url=module_data['url'],
                        defaults={
                            'name': module_data['name'],
                            'module_type': module_data['moduletype'],
                            'description': module_data['description'],
                            'icon': module_data['icon'],
                            'order': order,
                        },
                    )
                    if created:
                        created_modules += 1
                        if module_data['permissions']:
                            for permission in module_data['permissions']:
                                module.permissions.add(permission)
                    else:
                        if module_data['permissions'] and module.permissions.count() == 0:
                            for permission in module_data['permissions']:
                                module.permissions.add(permission)
                        update_fields = []
                        if module.order != order:
                            module.order = order
                            update_fields.append('order')
                            reordered_modules += 1
                        if module.module_type_id != (module_data['moduletype'].id if module_data['moduletype'] else None):
                            module.module_type = module_data['moduletype']
                            update_fields.append('module_type')
                            moved_modules += 1
                        if update_fields:
                            module.save(update_fields=update_fields)

                created_groups = 0
                linked_modules = 0
                revoked_permissions = 0
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
                        permissions = module.permissions.all()
                        if group_name == 'Punto de Venta':
                            permissions = permissions.exclude(codename__in=POINT_OF_SALE_NO_DELETE_CODENAMES)
                        for permission in permissions:
                            group.permissions.add(permission)

                    if group_name == 'Punto de Venta':
                        to_revoke = group.permissions.filter(codename__in=POINT_OF_SALE_NO_DELETE_CODENAMES)
                        revoked_permissions += to_revoke.count()
                        group.permissions.remove(*to_revoke)

                if created_modules or created_groups or linked_modules or reordered_modules or moved_modules or revoked_permissions:
                    self.stdout.write(self.style.SUCCESS(
                        f'{company.business_name} ({company.schema_name}): '
                        f'{created_modules} módulos creados, {created_groups} grupos creados, '
                        f'{linked_modules} asignaciones de módulo agregadas, '
                        f'{reordered_modules} módulos reordenados, '
                        f'{moved_modules} módulos movidos de tipo, '
                        f'{revoked_permissions} permisos de borrado revocados a Punto de Venta'
                    ))
                else:
                    self.stdout.write(f'{company.business_name} ({company.schema_name}): ya estaba al día')

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

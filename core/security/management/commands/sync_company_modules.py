from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from core.tenant.models import Company, EMPLOYEE_URLS, CLIENT_URLS, POINT_OF_SALE_URLS, POINT_OF_SALE_NO_DELETE_CODENAMES

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
        "mismas reglas de create_base_modules(), (4) revoca al grupo "
        "'Punto de Venta' los permisos de borrado de Cuentas por cobrar/pagar, "
        "Compras, Gastos, Retenciones y Ventas (esto último incluye anular un "
        "ticket) (reservados a Administrador), (5) otorga a "
        "Administrador el permiso view_cashregister (el Consolidado del "
        "dashboard y el 'cuadre de caja independiente' de Cuentas por "
        "Cobrar/Pagar dependen de él, pero no está ligado a ningún módulo "
        "navegable, así que create_base_modules() lo asigna aparte y este "
        "comando antes no lo replicaba en compañías ya existentes), y (6) "
        "agrega los permisos de Retención (nuevo, registro de comprobantes de "
        "retención desde Ventas > Opciones) al módulo Ventas ya existente, "
        "que de otro modo se queda solo con los permisos de Sale que tenía al "
        "crearse, y (7) activa GroupSettings.requires_cash_register=True para "
        "'Punto de Venta' incluso si el grupo ya existía de antes (antes solo "
        "se creaba 'if created', así que una compañía cuyo grupo 'Punto de "
        "Venta' ya existía antes de la función de apertura de caja al iniciar "
        "sesión se quedaba sin esta fila para siempre: sus usuarios nunca "
        "eran redirigidos a abrir caja al loguearse y el dashboard nunca les "
        "mostraba 'Mi Caja de hoy'). Seguro de volver a ejecutar, no duplica "
        "módulos ni permisos existentes -lo único que borra son esos permisos "
        "de borrado puntuales del grupo Punto de Venta."
    )

    def handle(self, *args, **options):
        from django.contrib.auth.models import Permission
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

                # Retención es nueva: el módulo Ventas ya existía con los
                # permisos de Sale, así que el "if module.permissions.count()
                # == 0" de arriba no aplica -mismo caso que view_cashregister-.
                # Se agregan los permisos de Retention al módulo Ventas si
                # faltan, para que las compañías ya existentes también puedan
                # registrar retenciones desde Ventas > Opciones.
                granted_retention = 0
                sale_module = Module.objects.filter(url='/pos/sale/admin/').first()
                if sale_module:
                    for permission in Permission.objects.filter(content_type__model='retention'):
                        if not sale_module.permissions.filter(id=permission.id).exists():
                            sale_module.permissions.add(permission)
                            granted_retention += 1

                created_groups = 0
                linked_modules = 0
                revoked_permissions = 0
                granted_cashregister = 0
                fixed_cash_register_settings = 0
                for group_name, urls in GROUP_URLS.items():
                    group, created = Group.objects.get_or_create(name=group_name)
                    if created:
                        created_groups += 1

                    if group_name == 'Punto de Venta':
                        # No solo "if created": una compañía cuyo grupo 'Punto
                        # de Venta' ya existía DE ANTES de que se implementara
                        # "apertura de caja al iniciar sesión" nunca pasaba por
                        # aquí, así que se quedaba sin esta fila -sus usuarios
                        # jamás eran redirigidos a abrir caja al loguearse, y
                        # por lo tanto el dashboard nunca mostraba su tarjeta
                        # "Mi Caja de hoy" (quedaba como si nunca hubieran
                        # abierto caja, aunque sí vendieran).
                        settings_obj, settings_created = GroupSettings.objects.get_or_create(
                            group=group, defaults={'requires_cash_register': True}
                        )
                        if not settings_created and not settings_obj.requires_cash_register:
                            settings_obj.requires_cash_register = True
                            settings_obj.save(update_fields=['requires_cash_register'])
                            fixed_cash_register_settings += 1
                        elif settings_created:
                            fixed_cash_register_settings += 1

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

                    if group_name == 'Administrador' and not group.permissions.filter(codename='view_cashregister').exists():
                        group.permissions.add(Permission.objects.get(codename='view_cashregister'))
                        granted_cashregister += 1

                if created_modules or created_groups or linked_modules or reordered_modules or moved_modules or revoked_permissions or granted_cashregister or granted_retention or fixed_cash_register_settings:
                    self.stdout.write(self.style.SUCCESS(
                        f'{company.business_name} ({company.schema_name}): '
                        f'{created_modules} módulos creados, {created_groups} grupos creados, '
                        f'{linked_modules} asignaciones de módulo agregadas, '
                        f'{reordered_modules} módulos reordenados, '
                        f'{moved_modules} módulos movidos de tipo, '
                        f'{revoked_permissions} permisos de borrado revocados a Punto de Venta, '
                        f'{granted_cashregister} view_cashregister otorgado a Administrador, '
                        f'{granted_retention} permisos de Retención agregados al módulo Ventas, '
                        f'{fixed_cash_register_settings} requires_cash_register activado para Punto de Venta'
                    ))
                else:
                    self.stdout.write(f'{company.business_name} ({company.schema_name}): ya estaba al día')

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

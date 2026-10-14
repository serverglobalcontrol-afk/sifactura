"""Crea (o repara) los módulos del RDEP en el menú de Recursos Humanos de una empresa.

Las empresas NUEVAS los reciben con los módulos base (Company.get_base_modules_data); las que
ya existían los obtienen con `manage.py activate_rdep_modules`. Es idempotente.
"""
from django.contrib.auth.models import Permission
from django.db import transaction
from django_tenants.utils import schema_context

MODULE_TYPE_NAME = 'Recursos Humanos'

# (nombre, url, icono, descripción, modelos cuyos permisos requiere, orden)
MODULES = [
    ('Anexo RDEP', '/rrhh/rdep/', 'fas fa-file-archive',
     'Revisa y descarga el RDEP del año, validado con el esquema oficial del SRI', ['rdepyear', 'rdeptaxbracket', 'rdepemployeeyear'], 89),
    ('Parámetros RDEP', '/rrhh/rdep/settings/', 'fas fa-file-invoice',
     'Tabla del impuesto a la renta y canasta familiar básica para el RDEP', ['rdepyear', 'rdeptaxbracket', 'rdepemployeeyear'], 90),
]


def activate_modules():
    """Crea los módulos en el schema ACTUAL y los asigna al grupo Administrador."""
    from core.security.models import Group, GroupModule, Module, ModuleType
    module_type, _ = ModuleType.objects.get_or_create(name=MODULE_TYPE_NAME, defaults={'icon': 'fas fa-users'})
    admin_group = Group.objects.filter(name='Administrador').first()
    created = 0
    for name, url, icon, description, models_, order in MODULES:
        module, was_created = Module.objects.get_or_create(
            url=url, defaults={'name': name, 'icon': icon, 'description': description, 'module_type': module_type, 'order': order})
        created += was_created
        permissions = list(Permission.objects.filter(content_type__app_label='rrhh', content_type__model__in=models_))
        if permissions:
            module.permissions.add(*permissions)
        if admin_group is not None:
            GroupModule.objects.get_or_create(module=module, group=admin_group)
            if permissions:
                admin_group.permissions.add(*permissions)
    return created


def sync_schema(schema_name):
    with schema_context(schema_name):
        with transaction.atomic():
            return activate_modules()

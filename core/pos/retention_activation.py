"""Activa o oculta el menú de Retenciones emitidas según `Company.retention_agent`.

Mismo criterio que la Contabilidad: el menú sale de las filas Module/GroupModule
del grupo, así que los módulos de retenciones emitidas NO se agregan a
Company.get_base_modules_data() (se crearían en todas las empresas); se crean
aquí solo cuando la empresa es agente de retención, y se ocultan (sin tocar los
datos) cuando deja de serlo.
"""
from django.contrib.auth.models import Permission
from django.db import transaction
from django_tenants.utils import schema_context

MODULE_TYPE_NAME = 'Facturación'

# (nombre, url, icono, descripción, modelos cuyos permisos requiere, orden)
MODULES = [
    ('Retenciones emitidas', '/pos/supplier/retention/', 'fas fa-file-invoice-dollar',
     'Retenciones emitidas a proveedores (comprobante electrónico)', ['supplierretention'], 6),
    ('Conceptos de retención', '/pos/retention/concept/', 'fas fa-percent',
     'Catálogo de conceptos y porcentajes de retención del SRI', ['retentionconcept'], 9),
]
URLS = [m[1] for m in MODULES]


def _activate():
    from core.security.models import Group, GroupModule, Module, ModuleType
    module_type = ModuleType.objects.filter(name=MODULE_TYPE_NAME).first()
    admin_group = Group.objects.filter(name='Administrador').first()
    for name, url, icon, description, models_, order in MODULES:
        module, _ = Module.objects.get_or_create(
            url=url, defaults={'name': name, 'icon': icon, 'description': description, 'module_type': module_type, 'order': order},
        )
        permissions = list(Permission.objects.filter(content_type__app_label='pos', content_type__model__in=models_))
        if permissions:
            module.permissions.add(*permissions)
        if admin_group is not None:
            GroupModule.objects.get_or_create(module=module, group=admin_group)
            if permissions:
                admin_group.permissions.add(*permissions)


def _deactivate():
    from core.security.models import Module
    Module.objects.filter(url__in=URLS).delete()


def sync_company_retention_modules(company):
    """Deja el menú de Retenciones emitidas en el estado que corresponde al
    flag `retention_agent` de la empresa. Idempotente."""
    with schema_context(company.scheme.schema_name):
        with transaction.atomic():
            if company.retention_agent == 'SI':
                _activate()
            else:
                _deactivate()

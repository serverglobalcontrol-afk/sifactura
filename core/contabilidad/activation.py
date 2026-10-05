"""Activa o desactiva el módulo de Contabilidad de una empresa según
`Company.obligated_accounting`.

El menú del sistema sale 100 % de las filas Module/GroupModule del grupo, así
que "ocultar" el módulo significa no tener esas filas. Por eso la contabilidad
NO se agrega a Company.get_base_modules_data() (eso la crearía en todas las
empresas): sus módulos se crean aquí solo cuando la empresa la lleva.
"""
from django.contrib.auth.models import Permission
from django.db import transaction
from django_tenants.utils import schema_context

from core.contabilidad import chart
from core.contabilidad.models import Account, AccountMapping, AccountingConfig

MODULE_TYPE_NAME = 'Contabilidad'
MODULE_TYPE_ICON = 'fas fa-book-open'  # ModuleType.icon es único: 'fa-calculator' ya lo usa Facturación

# (nombre, url, icono, descripción, modelos cuyos permisos requiere)
MODULES = [
    ('Configuración contable', '/contabilidad/config/', 'fas fa-cogs', 'Fecha de inicio, cuentas por rol y por tipo de gasto/ingreso', ['accountingconfig', 'accountmapping', 'typeaccountmapping']),
    ('Plan de cuentas', '/contabilidad/account/', 'fas fa-sitemap', 'Administra el plan de cuentas de la empresa', ['account']),
    ('Cuentas bancarias', '/contabilidad/bank/', 'fas fa-university', 'Cuentas bancarias, alias de banco y movimientos bancarios', ['bankaccount', 'bankalias']),
    ('Asientos contables', '/contabilidad/entry/', 'fas fa-book', 'Libro de asientos, asientos manuales y contabilización de pendientes', ['journalentry', 'journalentryline']),
    ('Períodos contables', '/contabilidad/period/', 'fas fa-calendar-check', 'Abrir y cerrar períodos contables', ['accountingperiod']),
    ('Libro diario', '/contabilidad/report/journal/', 'fas fa-file-alt', 'Reporte del libro diario', []),
    ('Libro mayor', '/contabilidad/report/ledger/', 'fas fa-file-invoice', 'Reporte del libro mayor por cuenta', []),
    ('Balance de comprobación', '/contabilidad/report/trial/', 'fas fa-balance-scale', 'Sumas y saldos por cuenta', []),
    ('Libro de banco', '/contabilidad/report/bank/', 'fas fa-money-check-alt', 'Movimientos por cuenta bancaria', []),
]


def seed_chart_of_accounts():
    """Crea el plan de cuentas base y los roles por defecto (idempotente: no
    pisa cuentas ni roles que la empresa ya haya editado)."""
    by_code = {}
    for code, name, account_type, accepts in chart.CHART:
        parent = by_code.get(code.rsplit('.', 1)[0]) if '.' in code else None
        account, _ = Account.objects.get_or_create(
            code=code,
            defaults={'name': name, 'account_type': account_type, 'accepts_movement': accepts, 'parent': parent, 'is_system': True},
        )
        by_code[code] = account
    for role, code in chart.DEFAULT_ROLE_ACCOUNTS.items():
        AccountMapping.objects.get_or_create(role=role, defaults={'account': by_code.get(code) or Account.objects.get(code=code)})


def _activate():
    from core.security.models import Group, GroupModule, Module, ModuleType
    seed_chart_of_accounts()
    AccountingConfig.objects.get_or_create(pk=1)
    module_type, _ = ModuleType.objects.get_or_create(name=MODULE_TYPE_NAME, defaults={'icon': MODULE_TYPE_ICON})
    admin_group = Group.objects.filter(name='Administrador').first()
    for order, (name, url, icon, description, models_) in enumerate(MODULES, start=1):
        module, created = Module.objects.get_or_create(
            url=url, defaults={'name': name, 'icon': icon, 'description': description, 'module_type': module_type, 'order': order},
        )
        if not created and module.module_type_id != module_type.pk:
            module.module_type = module_type
            module.save(update_fields=['module_type'])
        permissions = list(Permission.objects.filter(content_type__app_label='contabilidad', content_type__model__in=models_)) if models_ else []
        if permissions:
            module.permissions.add(*permissions)
        if admin_group is not None:
            GroupModule.objects.get_or_create(module=module, group=admin_group)
            if permissions:
                admin_group.permissions.add(*permissions)


def _deactivate():
    """Oculta el módulo: borra las filas Module (cascada a GroupModule). Los
    datos contables (asientos, cuentas) se CONSERVAN por si la empresa vuelve
    a llevar contabilidad."""
    from core.security.models import Module
    Module.objects.filter(url__startswith='/contabilidad/').delete()


def sync_company_accounting(company):
    """Deja el schema de `company` en el estado que corresponde a su flag
    `obligated_accounting`. Idempotente."""
    with schema_context(company.scheme.schema_name):
        with transaction.atomic():
            if company.obligated_accounting == 'SI':
                _activate()
            else:
                _deactivate()

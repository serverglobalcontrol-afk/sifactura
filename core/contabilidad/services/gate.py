from django.db import connection


def get_company():
    """Empresa del schema actual. Company vive en el schema `public`: nunca se
    debe usar Company.objects.first(), que devolvería la primera de TODO el
    sistema. Se toma de la relación inversa del tenant actual (en el schema
    `public` el tenant no tiene company y esto devuelve None)."""
    tenant = getattr(connection, 'tenant', None)
    return getattr(tenant, 'company', None)


def company_keeps_accounting(company=None):
    company = company if company is not None else get_company()
    return bool(company) and company.obligated_accounting == 'SI'


def is_enabled():
    """True solo si la empresa del schema actual lleva contabilidad Y ya está
    activada (existe su configuración)."""
    if not company_keeps_accounting():
        return False
    from core.contabilidad.models import AccountingConfig
    return AccountingConfig.objects.exists()

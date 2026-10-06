from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from core.contabilidad.activation import sync_company_accounting
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        'Activa el módulo de Contabilidad en las empresas que llevan contabilidad '
        '(obligated_accounting = SI) y lo oculta en las que no. Es idempotente: se '
        'puede correr varias veces. Úsalo tras el despliegue para las empresas que '
        'ya estaban marcadas como SI.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Limitar a un solo schema (por defecto todas las empresas).')

    def handle(self, *args, **options):
        with schema_context('public'):
            companies = list(Company.objects.select_related('scheme').all())
        for company in companies:
            if options['schema'] and company.scheme.schema_name != options['schema']:
                continue
            sync_company_accounting(company)
            state = 'ACTIVADA' if company.uses_accounting_module else 'oculta (no lleva contabilidad)'
            self.stdout.write(f'{company.scheme.schema_name}: contabilidad {state}')

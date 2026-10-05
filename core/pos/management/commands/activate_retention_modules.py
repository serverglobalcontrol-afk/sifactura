from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from core.pos.retention_activation import sync_company_retention_modules
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        'Muestra el menú de Retenciones emitidas en las empresas que son agente de retención '
        '(retention_agent = SI) y lo oculta en las demás. Idempotente: úsalo tras el despliegue '
        'para las empresas que ya estaban marcadas como agente de retención.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Limitar a un solo schema (por defecto todas las empresas).')

    def handle(self, *args, **options):
        with schema_context('public'):
            companies = list(Company.objects.select_related('scheme').all())
        for company in companies:
            if options['schema'] and company.scheme.schema_name != options['schema']:
                continue
            sync_company_retention_modules(company)
            state = 'VISIBLE' if company.retention_agent == 'SI' else 'oculto (no es agente de retención)'
            self.stdout.write(f'{company.scheme.schema_name}: retenciones emitidas {state}')

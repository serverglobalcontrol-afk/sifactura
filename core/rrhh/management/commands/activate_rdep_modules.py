from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from core.rrhh.rdep_activation import sync_schema
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        'Agrega los módulos del RDEP (Parámetros RDEP y, cuando exista, el anexo) al menú de Recursos '
        'Humanos de las empresas ya creadas. Idempotente: úsalo tras cada despliegue que agregue módulos del RDEP.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Limitar a un solo schema (por defecto todas las empresas).')

    def handle(self, *args, **options):
        with schema_context('public'):
            companies = list(Company.objects.select_related('scheme').all())
        for company in companies:
            name = company.scheme.schema_name
            if options['schema'] and name != options['schema']:
                continue
            created = sync_schema(name)
            self.stdout.write(f'{name}: módulos del RDEP listos ({created} nuevo(s))')

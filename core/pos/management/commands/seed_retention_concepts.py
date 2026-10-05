from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from core.pos.retention_catalog import SOURCE, seed_retention_concepts
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        'Agrega los conceptos de retención (renta e IVA) del catálogo oficial que falten en cada '
        'empresa. Nunca modifica los que ya existen (la empresa pudo ajustar su porcentaje).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Limitar a un solo schema (por defecto todas las empresas).')

    def handle(self, *args, **options):
        from core.pos.models import RetentionConcept

        with schema_context('public'):
            companies = list(Company.objects.select_related('scheme').all())
        for company in companies:
            name = company.scheme.schema_name
            if options['schema'] and name != options['schema']:
                continue
            with schema_context(name):
                created = seed_retention_concepts(RetentionConcept)
            self.stdout.write(f'{name}: {created} concepto(s) agregado(s)')
        self.stdout.write(f'Fuente: {SOURCE}')

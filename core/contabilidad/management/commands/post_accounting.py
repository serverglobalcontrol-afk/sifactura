from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from core.contabilidad.services.gate import company_keeps_accounting
from core.contabilidad.services.posting import post_pending
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        'Contabiliza los documentos pendientes de un rango de fechas (ventas, cobros, '
        'compras, gastos...) en las empresas que llevan contabilidad. No duplica '
        'asientos: es el mismo barrido del botón "Contabilizar pendientes".'
    )

    def add_arguments(self, parser):
        parser.add_argument('--schema', help='Limitar a un solo schema (por defecto todas las que llevan contabilidad).')
        parser.add_argument('--desde', required=True, help='Fecha inicial YYYY-MM-DD')
        parser.add_argument('--hasta', default=date.today().strftime('%Y-%m-%d'), help='Fecha final YYYY-MM-DD (por defecto hoy)')

    def handle(self, *args, **options):
        try:
            start = datetime.strptime(options['desde'], '%Y-%m-%d').date()
            end = datetime.strptime(options['hasta'], '%Y-%m-%d').date()
        except ValueError:
            raise CommandError('Las fechas deben tener el formato YYYY-MM-DD.')
        with schema_context('public'):
            companies = list(Company.objects.select_related('scheme').all())
        for company in companies:
            name = company.scheme.schema_name
            if options['schema'] and name != options['schema']:
                continue
            if not company_keeps_accounting(company):
                continue
            with schema_context(name):
                from core.contabilidad.models import AccountingConfig
                if not AccountingConfig.objects.exists():
                    self.stdout.write(self.style.WARNING(f'{name}: contabilidad no activada (corre activate_accounting).'))
                    continue
                summary, errors = post_pending(start, end)
            self.stdout.write(f'{name}: {summary}')
            for error in errors:
                self.stdout.write(self.style.ERROR(f'  {error}'))

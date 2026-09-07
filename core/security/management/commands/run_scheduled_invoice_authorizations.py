from django.core.management import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from core.pos.choices import INVOICE_STATUS, VOUCHER_TYPE
from core.pos.utilities.sri import SRI
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        "Genera ante el SRI la autorización pendiente de las facturas que quedaron "
        "'Sin Autorizar' (por ejemplo porque el SRI no estaba disponible al momento "
        "de la venta), en cada compañía que tenga esta gestión automática habilitada "
        "y cuya hora configurada ya se cumplió. Debe programarse para correr "
        "periódicamente (por ejemplo cada 10 minutos) mediante una tarea del sistema "
        "operativo (cron / Programador de tareas)."
    )

    def handle(self, *args, **options):
        from core.pos.models import Sale

        now = timezone.localtime()

        with schema_context('public'):
            companies = list(Company.objects.filter(active=True, invoice_auto_authorization_enabled=True))

        self.stdout.write(f'Compañías con autorización automática de facturas habilitada: {len(companies)}')

        for company in companies:
            if not company.is_invoice_auto_authorization_due(now):
                continue
            authorized, failed = 0, 0
            with schema_context(company.schema_name):
                queryset = Sale.objects.filter(status=INVOICE_STATUS[0][0], receipt__voucher_type=VOUCHER_TYPE[0][0])
                for sale in queryset:
                    result = sale.generate_electronic_invoice()
                    if 'error' in result:
                        SRI().create_voucher_errors(sale, result)
                    if result.get('resp'):
                        authorized += 1
                    else:
                        failed += 1
            with schema_context('public'):
                company.mark_invoice_auto_authorization_run(now)
            self._report(company.business_name, authorized, failed)

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

    def _report(self, label, authorized, failed):
        if failed:
            self.stdout.write(self.style.WARNING(f'{label}: {authorized} factura(s) autorizada(s), {failed} pendiente(s) o con error'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{label}: {authorized} factura(s) autorizada(s)'))

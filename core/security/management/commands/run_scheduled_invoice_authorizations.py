from django.core.management import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from core.pos.choices import INVOICE_STATUS, VOUCHER_TYPE
from core.pos.utilities.sri import SRI
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        "Revisa el estado real de cada comprobante pendiente: genera ante el SRI la "
        "autorización de las facturas que quedaron 'Sin Autorizar' (por ejemplo porque "
        "el SRI no estaba disponible al momento de la venta), y además envía por "
        "correo las que el SRI ya autorizó pero se quedaron sin enviar. Corre en cada "
        "compañía que tenga esta gestión automática habilitada y cuya hora configurada "
        "ya se cumplió. Debe programarse para correr periódicamente (por ejemplo cada "
        "10 minutos) mediante una tarea del sistema operativo (cron / Programador de "
        "tareas)."
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
            sri = SRI()
            authorized, emailed, failed = 0, 0, 0
            with schema_context(company.schema_name):
                pending_authorization = Sale.objects.filter(status=INVOICE_STATUS[0][0], receipt__voucher_type=VOUCHER_TYPE[0][0])
                for sale in pending_authorization:
                    result = sale.generate_electronic_invoice()
                    if 'error' in result:
                        sri.create_voucher_errors(sale, result)
                    if result.get('resp'):
                        authorized += 1
                    else:
                        failed += 1
                pending_email = Sale.objects.filter(status=INVOICE_STATUS[1][0], receipt__voucher_type=VOUCHER_TYPE[0][0])
                for sale in pending_email:
                    result = sri.notify_by_email(instance=sale, company=sale.company, client=sale.client)
                    if result.get('resp'):
                        emailed += 1
                    else:
                        failed += 1
            with schema_context('public'):
                company.mark_invoice_auto_authorization_run(now)
            self._report(company.business_name, authorized, emailed, failed)

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

    def _report(self, label, authorized, emailed, failed):
        summary = f'{authorized} factura(s) autorizada(s), {emailed} enviada(s) por correo'
        if failed:
            self.stdout.write(self.style.WARNING(f'{label}: {summary}, {failed} pendiente(s) o con error'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{label}: {summary}'))

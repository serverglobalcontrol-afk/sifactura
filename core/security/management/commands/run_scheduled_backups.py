from django.core.management import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from core.security.backups import create_postgresql_backup
from core.tenant.models import Company, ElectronicInvoicingProvider
from core.user.models import User


class Command(BaseCommand):
    help = (
        "Ejecuta los respaldos automáticos programados (por compañía y el respaldo "
        "general del sistema) que ya estén vencidos según su horario configurado. "
        "Debe programarse para correr periódicamente (por ejemplo cada 15 minutos) "
        "mediante una tarea del sistema operativo (cron / Programador de tareas)."
    )

    def handle(self, *args, **options):
        now = timezone.localtime()

        with schema_context('public'):
            provider = ElectronicInvoicingProvider.objects.first()
            if provider and provider.is_backup_due(now):
                system_user = User.objects.filter(is_superuser=True).first()
                if system_user:
                    result = create_postgresql_backup(system_user)
                    provider.mark_backup_run(now)
                    self._report('Sistema (respaldo general)', result)
                else:
                    self.stdout.write(self.style.WARNING(
                        'Respaldo del sistema: no hay un usuario administrador en public para asociar el respaldo'
                    ))

            companies = list(Company.objects.filter(active=True, backup_schedule_enabled=True))

        self.stdout.write(f'Compañías con respaldo programado habilitado: {len(companies)}')

        for company in companies:
            if not company.is_backup_due(now):
                continue
            with schema_context(company.schema_name):
                system_user = User.objects.filter(is_superuser=True).first()
                if not system_user:
                    self.stdout.write(self.style.WARNING(
                        f'{company.business_name}: no hay un usuario administrador para asociar el respaldo'
                    ))
                    continue
                result = create_postgresql_backup(system_user)
            with schema_context('public'):
                company.mark_backup_run(now)
            self._report(company.business_name, result)

        self.stdout.write(self.style.SUCCESS('Proceso completado'))

    def _report(self, label, result):
        if result.get('error'):
            self.stdout.write(self.style.ERROR(f'{label}: error al generar el respaldo: {result["error"]}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{label}: respaldo generado correctamente'))

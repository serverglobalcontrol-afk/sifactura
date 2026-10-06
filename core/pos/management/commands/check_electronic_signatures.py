import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from config import settings
from core.pos.utilities.sri import signature_validity
from core.tenant.models import Company


class Command(BaseCommand):
    help = (
        'Muestra la vigencia del certificado de firma electrónica (.p12) de cada empresa y la fecha del '
        'servidor. Un certificado vencido (o que aún no inicia su vigencia) hace que el SRI rechace TODAS '
        'las facturas con "FIRMA INVALIDA".'
    )

    def handle(self, *args, **options):
        now = datetime.now(timezone.utc)
        self.stdout.write(f'Fecha y hora del servidor (UTC): {now:%Y-%m-%d %H:%M:%S}\n')
        with schema_context('public'):
            companies = list(Company.objects.select_related('scheme').order_by('id'))
        for company in companies:
            name = company.scheme.schema_name
            label = f'{name:15}'
            path = f'{settings.BASE_DIR}/{company.get_electronic_signature()}' if company.electronic_signature else None
            if not path or not os.path.exists(path):
                self.stdout.write(self.style.WARNING(f'{label} sin certificado cargado'))
                continue
            with open(path, 'rb') as file:
                validity = signature_validity(file.read(), company.electronic_signature_key)
            if validity is None:
                self.stdout.write(self.style.ERROR(f'{label} no se pudo leer el certificado (clave incorrecta o archivo dañado)'))
                continue
            start, end = validity
            days = (end - now).days
            period = f'vigente desde {start:%Y-%m-%d} hasta {end:%Y-%m-%d}'
            if now > end:
                self.stdout.write(self.style.ERROR(f'{label} VENCIDO hace {-days} día(s) ({period})'))
            elif now < start:
                self.stdout.write(self.style.ERROR(f'{label} AÚN NO VIGENTE ({period})'))
            elif days <= 30:
                self.stdout.write(self.style.WARNING(f'{label} vence en {days} día(s) ({period})'))
            else:
                self.stdout.write(self.style.SUCCESS(f'{label} vigente, {days} día(s) restantes ({period})'))

import gzip
import os
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_tenants.utils import schema_context

TABLE = 'public.tenant_sriruc'
NEW = 'tenant_sriruc_new'


class Command(BaseCommand):
    help = ('Carga el archivo reducido (de `build_sri_catalog`) en la tabla compartida del catálogo SRI. Arma una tabla nueva '
            'aparte y la intercambia al final, así las consultas no se bloquean mientras se importa.')

    def add_arguments(self, parser):
        parser.add_argument('file', help='Archivo .csv.gz generado por build_sri_catalog')
        parser.add_argument('--date', help='Fecha de los datos del SRI (AAAA-MM-DD); por defecto, la fecha de hoy')

    def handle(self, *args, **options):
        path = options['file']
        if not os.path.isfile(path):
            raise CommandError(f'No existe: {path}')
        catalog_date = date.fromisoformat(options['date']) if options['date'] else date.today()
        with schema_context('public'):
            cursor = connection.cursor()
            cursor.execute(f'DROP TABLE IF EXISTS public.{NEW}')
            cursor.execute(f'CREATE TABLE public.{NEW} (LIKE {TABLE} INCLUDING DEFAULTS)')
            cursor.execute('DROP TABLE IF EXISTS pg_temp.sri_stage')
            cursor.execute('CREATE TEMP TABLE sri_stage (ruc varchar(13), business_name text, trade_name text, status text, taxpayer_type text, '
                           'accounting char(1), province text, canton text, establishment text)')
            self.stdout.write('Leyendo el archivo...')
            with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
                cursor.cursor.copy_expert("COPY sri_stage FROM STDIN WITH (FORMAT text, DELIMITER '|', NULL '')", f)
            cursor.execute('SELECT count(*) FROM sri_stage')
            staged = cursor.fetchone()[0]
            if not staged:
                raise CommandError('El archivo no tiene filas.')
            self.stdout.write(f'{staged} filas leídas; quitando duplicados por RUC...')
            cursor.execute(
                f'INSERT INTO public.{NEW} (ruc, business_name, trade_name, status, taxpayer_type, accounting_required, province, canton, catalog_date) '
                "SELECT DISTINCT ON (ruc) ruc, left(business_name, 300), NULLIF(left(trade_name, 300), ''), left(status, 30), NULLIF(left(taxpayer_type, 30), ''), "
                "(accounting = 'S'), NULLIF(left(province, 60), ''), NULLIF(left(canton, 60), ''), %s "
                "FROM sri_stage WHERE status IN ('ACTIVO', 'SUSPENDIDO', 'PASIVO') ORDER BY ruc, establishment", [catalog_date])
            cursor.execute(f'ALTER TABLE public.{NEW} ADD PRIMARY KEY (ruc)')
            cursor.execute(f'SELECT count(*) FROM public.{NEW}')
            total = cursor.fetchone()[0]
            with transaction.atomic():
                cursor.execute(f'ALTER TABLE {TABLE} RENAME TO tenant_sriruc_old')
                cursor.execute(f'ALTER TABLE public.{NEW} RENAME TO tenant_sriruc')
                cursor.execute('DROP TABLE public.tenant_sriruc_old')
                cursor.execute(f'ALTER INDEX IF EXISTS public.{NEW}_pkey RENAME TO tenant_sriruc_pkey')
            cursor.execute('ANALYZE public.tenant_sriruc')
        self.stdout.write(self.style.SUCCESS(f'Catálogo SRI cargado: {total} RUC (datos al {catalog_date}).'))

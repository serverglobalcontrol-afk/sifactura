import os

from django.core.management.base import BaseCommand, CommandError

from core.tenant.sri_catalog import build_slim_file


class Command(BaseCommand):
    help = 'Reduce los archivos de contribuyentes del SRI (carpeta, .zip o .csv) a un solo archivo ligero para `import_sri_catalog`.'

    def add_arguments(self, parser):
        parser.add_argument('source', help='Carpeta con los CSV/ZIP del SRI, un .zip o un .csv')
        parser.add_argument('--out', default='sri_catalog.csv.gz', help='Archivo de salida (gzip)')

    def handle(self, *args, **options):
        source, out = options['source'], options['out']
        if not os.path.exists(source):
            raise CommandError(f'No existe: {source}')
        rows, files = build_slim_file(source, out, progress=lambda name, total: self.stdout.write(f'{name}: acumulado {total} filas'))
        if not files:
            raise CommandError('No se encontró ningún .csv (ni dentro de .zip) en esa ruta.')
        self.stdout.write(self.style.SUCCESS(f'{files} archivo(s), {rows} filas -> {out} ({os.path.getsize(out) / 1048576:.1f} MB)'))

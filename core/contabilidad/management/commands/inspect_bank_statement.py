from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from core.contabilidad.services import reconciliation


class Command(BaseCommand):
    help = (
        'Diagnóstico de un estado de cuenta (PDF, Excel o CSV): muestra el texto que se extrae y los movimientos que el sistema '
        'entiende, SIN guardar nada. Úsalo cuando un archivo no se lee bien en Conciliación bancaria.'
    )

    def add_arguments(self, parser):
        parser.add_argument('path', help='Ruta del archivo en el servidor.')
        parser.add_argument('--opening', help='Saldo inicial según el banco (ayuda a leer el signo en PDF).')
        parser.add_argument('--year', type=int, help='Año, si las fechas del PDF no lo traen (ej. 11-ago.).')
        parser.add_argument('--lines', type=int, default=40, help='Cuántas líneas del texto extraído mostrar (PDF).')

    def handle(self, *args, **options):
        try:
            with open(options['path'], 'rb') as f:
                data = f.read()
        except OSError as e:
            raise CommandError(f'No pude abrir el archivo: {e}')
        try:
            opening = Decimal(options['opening']) if options['opening'] else None
        except InvalidOperation:
            raise CommandError('El saldo inicial no es un número válido.')
        name = options['path'].lower()
        if name.endswith('.pdf') or data[:4] == b'%PDF':
            self.stdout.write('--- TEXTO EXTRAÍDO DEL PDF (primeras líneas, tal como lo ve el lector) ---')
            try:
                text = reconciliation._pdf_text(data)
            except reconciliation.StatementError as e:
                raise CommandError(str(e))
            shown = [l for l in text.splitlines() if l.strip()][:options['lines']]
            for line in shown:
                self.stdout.write(f'  {line!r}')
        self.stdout.write('\n--- MOVIMIENTOS QUE EL SISTEMA ENTIENDE ---')
        try:
            rows, warnings, source = reconciliation.parse_statement_file(data, options['path'], opening, options['year'])
        except reconciliation.StatementError as e:
            self.stdout.write(self.style.ERROR(f'No se pudo leer: {e}'))
            return
        self.stdout.write(f'Formato: {source}. Movimientos: {len(rows)}')
        for r in rows:
            self.stdout.write(f'  {r["date"]}  {str(r["amount"]).rjust(10)}  saldo {str(r["balance"]).rjust(10)}  ref {r["reference"]:<12} {r["description"]}')
        for w in warnings:
            self.stdout.write(self.style.WARNING(f'AVISO: {w}'))
        if rows:
            total = sum((r['amount'] for r in rows), Decimal('0'))
            self.stdout.write(f'\nNeto de los movimientos: {total}. Si el PDF trae saldo inicial y final, debe cumplirse: inicial + neto = final.')

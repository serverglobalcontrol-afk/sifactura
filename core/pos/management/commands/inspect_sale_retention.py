from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from core.pos.models import Retention, Sale

CENT = Decimal('0.01')


class Command(BaseCommand):
    help = (
        'Revisión de SOLO LECTURA de una factura de venta: sus retenciones recibidas (las que le hicieron los clientes), '
        'la cuenta por cobrar y los abonos, con comprobaciones de que los valores cuadren. No modifica nada.'
    )

    def add_arguments(self, parser):
        parser.add_argument('voucher', help='Número de la factura, completo (001-002-000000266) o solo el secuencial (266).')
        parser.add_argument('--schema', required=True, help='Empresa (schema), por ejemplo globalcontrol.')

    def handle(self, *args, **options):
        with schema_context(options['schema']):
            wanted = options['voucher'].strip()
            sales = Sale.objects.select_related('client__user', 'receipt')
            matches = list(sales.filter(voucher_number_full=wanted)) or list(sales.filter(voucher_number=wanted.zfill(9)))
            if not matches:
                raise CommandError(f'No encontré la factura {wanted} en {options["schema"]}.')
            for sale in matches:
                self.report(sale)

    def line(self, text, level='ok'):
        marks = {'ok': '  OK   ', 'warn': ' AVISO ', 'bad': ' REVISAR'}
        style = {'ok': self.style.SUCCESS, 'warn': self.style.WARNING, 'bad': self.style.ERROR}[level]
        self.stdout.write(style(f'{marks[level]} {text}'))

    def report(self, sale):
        subtotal = Decimal(sale.subtotal_12) + Decimal(sale.subtotal_0)
        self.stdout.write(f'\nFACTURA {sale.voucher_number_full}  cliente: {sale.client.user.names} ({sale.client.dni})  fecha: {sale.date_joined}')
        self.stdout.write(f'  Subtotal sin impuestos ${subtotal}  IVA ${sale.total_iva}  Total ${sale.total}  estado: {sale.get_status_display()}')
        retentions = list(Retention.objects.filter(sale=sale).order_by('id'))
        if not retentions:
            self.line('No tiene retenciones registradas.', 'warn')
        total_retained = Decimal('0')
        for r in retentions:
            self.stdout.write(f'\n  RETENCIÓN {r.document_number}  emitida {r.issue_date}  registrada {r.date_joined:%Y-%m-%d %H:%M}  por {r.created_by}')
            self.stdout.write(f'    Agente que retuvo: {r.agent_name or "-"} ({r.agent_ruc or "-"})   IVA ${r.iva_retained}   Renta ${r.income_tax_retained}   Total ${r.total_retained}')
            total_retained += Decimal(r.total_retained)
            iva, renta, total = Decimal(r.iva_retained), Decimal(r.income_tax_retained), Decimal(r.total_retained)
            self.line('IVA + Renta = total retenido' if (iva + renta).quantize(CENT) == total.quantize(CENT) else f'IVA + Renta = ${iva + renta}, pero el total retenido dice ${total}.', 'ok' if (iva + renta).quantize(CENT) == total.quantize(CENT) else 'bad')
            sale_iva = Decimal(sale.total_iva)
            if iva > sale_iva:
                self.line(f'El IVA retenido (${iva}) es MAYOR que el IVA de la factura (${sale_iva}).', 'bad')
            elif sale_iva > 0 and iva > 0:
                self.line(f'IVA retenido = {(iva / sale_iva * 100).quantize(CENT)}% del IVA de la factura (lo habitual: 10, 20, 30, 50, 70 o 100%).')
            if renta > subtotal:
                self.line(f'La renta retenida (${renta}) es MAYOR que el subtotal de la factura (${subtotal}).', 'bad')
            elif subtotal > 0 and renta > 0:
                self.line(f'Renta retenida = {(renta / subtotal * 100).quantize(CENT)}% del subtotal (lo habitual: 1, 1.75, 2, 2.75, 8 o 10%).')
            if total > Decimal(sale.total):
                self.line(f'El total retenido (${total}) es MAYOR que el total de la factura (${sale.total}).', 'bad')
            if r.agent_ruc and r.agent_ruc.strip() != (sale.client.dni or '').strip():
                self.line(f'El RUC del agente ({r.agent_ruc}) no es el del cliente de la factura ({sale.client.dni}).', 'warn')
            if r.issue_date < sale.date_joined:
                self.line(f'La retención ({r.issue_date}) es anterior a la factura ({sale.date_joined}).', 'bad')
            if r.access_code and not (r.access_code.isdigit() and len(r.access_code) == 49):
                self.line('La clave de acceso no tiene 49 dígitos.', 'warn')
        for ctas in sale.ctascollect_set.order_by('id'):
            self.stdout.write(f'\n  CUENTA POR COBRAR #{ctas.id:06d}: deuda ${ctas.debt}  saldo ${ctas.saldo}  estado: {"Adeuda" if ctas.state else "Pagada"}')
            paid = Decimal('0')
            retained = Decimal('0')
            for p in ctas.paymentsctacollect_set.order_by('date_joined', 'id'):
                kind = 'RETENCIÓN' if p.retention_id else 'pago'
                self.stdout.write(f'    {p.date_joined:%Y-%m-%d %H:%M}  {kind:<9} ${str(p.valor):>8}  {p.get_payment_type_display()}  {p.description or ""}')
                if p.retention_id:
                    retained += Decimal(p.valor)
                else:
                    paid += Decimal(p.valor)
            expected = (Decimal(ctas.debt) - paid - retained).quantize(CENT)
            self.line(f'Deuda ${ctas.debt} - pagos ${paid} - retenciones ${retained} = ${expected}' + ('' if expected == Decimal(ctas.saldo) else f' (pero el saldo guardado es ${ctas.saldo})'), 'ok' if expected == Decimal(ctas.saldo) else 'bad')
            if retained != total_retained.quantize(CENT):
                self.line(f'Lo descontado por retenciones (${retained}) no es igual al total de las retenciones registradas (${total_retained}).', 'warn')
            if bool(ctas.state) != (Decimal(ctas.saldo) > 0):
                self.line('El estado no corresponde al saldo.', 'bad')
        self.stdout.write('')

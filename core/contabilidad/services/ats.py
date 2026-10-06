"""Anexo Transaccional Simplificado (ATS) del SRI.

Se arma un archivo por mes (ATmmaaaa.xml dentro de ATmmaaaa.zip) con la
estructura del esquema oficial `ats.xsd` y la Ficha Técnica del ATS (feb-2025):

  * compras  : las compras REGISTRADAS en el mes (fecha de registro contable),
               con su IVA, el sustento tributario y las retenciones que la
               empresa emitió y el SRI autorizó.
  * ventas   : facturas y notas de crédito AUTORIZADAS del mes, acumuladas por
               cliente y tipo de comprobante, más las retenciones que los
               clientes le practicaron.
  * ventasEstablecimiento y anulados.

Se separa en tres pasos para poder probarlos por separado:
  collect_month()  -> datos en estructuras simples (lee la base de datos)
  render_xml()     -> XML (sin base de datos)
  validate_xml()   -> errores contra el XSD oficial

NO se inventan datos: lo que falta o no cuadra se informa como aviso ('error' si
impide presentar el anexo, 'warning' si conviene revisarlo) para que se corrija
en el sistema antes de descargar.
"""
import io
import re
import unicodedata
import zipfile
from calendar import monthrange
from collections import OrderedDict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from lxml import etree

from core.pos.choices import INVOICE_STATUS, RETENTION_KIND, VOUCHER_TYPE
from core.pos.utilities.xsd import XSD_DIR

CENT = Decimal('0.01')
ZERO = Decimal('0.00')
AUTHORIZED = (INVOICE_STATUS[1][0], INVOICE_STATUS[2][0])
CANCELED = INVOICE_STATUS[3][0]
MAX_MONTHS = 36

# Tabla 2 del ATS (compras): 01 RUC, 02 cédula, 03 pasaporte / identificación del exterior.
# Ventas (Tabla 2): 04 RUC, 05 cédula, 06 pasaporte, 07 consumidor final.
CONSUMER_FINAL_ID = '9999999999999'
# Comprobantes que no tienen numeración/autorización de imprenta: el SRI pide nueves.
NO_AUTHORIZATION_TYPES = ('11', '19', '20')
# Retención de IVA por porcentaje -> campo del ATS (compras).
IVA_RETENTION_FIELDS = OrderedDict([
    (10, 'valRetBien10'), (20, 'valRetServ20'), (30, 'valorRetBienes'),
    (50, 'valRetServ50'), (70, 'valorRetServicios'), (100, 'valRetServ100'),
])
# Forma de pago/cobro (Tabla 13) obligatoria cuando bases + impuestos superan este valor.
PAYMENT_METHOD_THRESHOLD = Decimal('500.00')

_schema = None


# ------------------------------------------------------------------ utilidades
def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return f'{money(value):.2f}'


def clean_name(value, minimum=1):
    """El ATS solo admite letras sin tilde, números y espacios en los nombres."""
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^A-Za-z0-9 ]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()[:500]
    return text if len(text) >= minimum else ''


def split_number(number):
    """'001002000004521' -> ('001', '002', 4521); None si no son 15 dígitos."""
    number = str(number or '').strip()
    if len(number) != 15 or not number.isdigit():
        return None
    return number[:3], number[3:6], int(number[6:])


def date_text(value):
    return value.strftime('%d/%m/%Y')


def month_label(year, month):
    return f'{month:02d}/{year}'


def zip_name(year, month):
    return f'AT{month:02d}{year}'


def months_between(start, end):
    """Lista de (año, mes) entre dos 'YYYY-MM' inclusive."""
    sy, sm = (int(x) for x in start.split('-'))
    ey, em = (int(x) for x in end.split('-'))
    if (ey, em) < (sy, sm):
        raise ValueError('El mes final no puede ser anterior al inicial.')
    months = []
    year, month = sy, sm
    while (year, month) <= (ey, em):
        months.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    if len(months) > MAX_MONTHS:
        raise ValueError(f'Elige un rango de máximo {MAX_MONTHS} meses.')
    return months


class Issues:
    def __init__(self):
        self.items = []

    def error(self, document, message):
        self.items.append({'level': 'error', 'document': document, 'message': message})

    def warning(self, document, message):
        self.items.append({'level': 'warning', 'document': document, 'message': message})

    def info(self, document, message):
        self.items.append({'level': 'info', 'document': document, 'message': message})

    @property
    def has_errors(self):
        return any(i['level'] == 'error' for i in self.items)


def _id_type_purchase(provider, issues, doc):
    code = provider.id_type if provider.id_type in ('01', '02', '03') else '01'
    ruc = (provider.ruc or '').strip()
    if code == '01' and not (len(ruc) == 13 and ruc.isdigit() and ruc.endswith('001')):
        issues.warning(doc, f'El RUC del proveedor "{ruc}" no parece válido (13 dígitos terminados en 001).')
    if code == '02' and not (len(ruc) == 10 and ruc.isdigit()):
        issues.warning(doc, f'La cédula del proveedor "{ruc}" no parece válida (10 dígitos).')
    return code, ruc[:13]


def _id_type_sale(client, issues, doc):
    """(tipo ATS ventas, identificación). 04 RUC, 05 cédula, 06 pasaporte, 07 consumidor final."""
    code = client.identification_type
    dni = (client.dni or '').strip()
    if code == '07':
        return '07', CONSUMER_FINAL_ID
    if code not in ('04', '05', '06'):
        issues.warning(doc, f'El tipo de identificación del cliente "{client.user.names}" ({code}) no se admite en ventas del ATS; se reporta como pasaporte.')
        code = '06'
    if code == '04' and not (len(dni) == 13 and dni.isdigit() and dni.endswith('001')):
        issues.warning(doc, f'El RUC del cliente "{client.user.names}" ({dni}) no parece válido (13 dígitos terminados en 001).')
    if code == '05' and not (len(dni) == 10 and dni.isdigit()):
        issues.warning(doc, f'La cédula del cliente "{client.user.names}" ({dni}) no parece válida (10 dígitos).')
    return code, dni[:13]


# ------------------------------------------------------------------- recolección
def collect_month(company, year, month):
    """Lee la base de datos (schema actual) y devuelve los datos del mes."""
    from core.pos.models import (
        CreditNote, Purchase, Receipt, Retention, Sale, SupplierRetention,
    )

    issues = Issues()
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])

    data = {
        'year': year, 'month': month,
        'ruc': company.ruc, 'name': clean_name(company.business_name, 5),
        'purchases': [], 'sales': OrderedDict(), 'establishments': OrderedDict(), 'canceled': [],
        'stats': {},
    }
    if not (len(company.ruc or '') == 13 and company.ruc.isdigit() and company.ruc.endswith('001')):
        issues.error('Empresa', f'El RUC de la empresa ({company.ruc}) debe tener 13 dígitos y terminar en 001.')
    if not data['name']:
        issues.error('Empresa', 'La razón social de la empresa debe tener al menos 5 letras o números.')

    # ---- compras
    purchases = Purchase.objects.filter(date_joined__year=year, date_joined__month=month).select_related('provider').order_by('date_joined', 'id')
    retentions_by_purchase = {}
    for retention in SupplierRetention.objects.filter(purchase__in=purchases).select_related('purchase').prefetch_related('supplierretentiondetail_set__concept').order_by('id'):
        retentions_by_purchase.setdefault(retention.purchase_id, []).append(retention)
    purchase_count = 0
    for purchase in purchases:
        doc = f'Compra {purchase.number}'
        record = _purchase_record(company, purchase, retentions_by_purchase.get(purchase.pk, []), issues, doc)
        if record:
            data['purchases'].append(record)
            purchase_count += 1
    data['stats']['purchases'] = purchase_count

    # ---- ventas: facturas y notas de crédito autorizadas
    sales = list(Sale.objects.filter(date_joined__range=(first, last), receipt__voucher_type=VOUCHER_TYPE[0][0]).select_related('client__user', 'receipt'))
    pending = [s for s in sales if s.status not in AUTHORIZED and s.status != CANCELED]
    if pending:
        numbers = ', '.join(s.voucher_number_full for s in pending[:8]) + ('…' if len(pending) > 8 else '')
        issues.warning('Ventas', f'{len(pending)} factura(s) del mes NO están autorizadas por el SRI y no se incluyen: {numbers}. Autorízalas (o anúlalas) antes de presentar el anexo.')
    for sale in sales:
        if sale.status not in AUTHORIZED:
            continue
        _add_sale_row(data, sale.client, VOUCHER_TYPE[0][0], sale.receipt.establishment_code, sale.subtotal_0, sale.subtotal_12, sale.total_iva, sale.payment_method, issues, f'Factura {sale.voucher_number_full}', count=1)
    credit_notes = CreditNote.objects.filter(date_joined__year=year, date_joined__month=month, receipt__voucher_type=VOUCHER_TYPE[1][0]).select_related('sale__client__user', 'receipt')
    pending_nc = [n for n in credit_notes if n.status not in AUTHORIZED and n.status != CANCELED]
    if pending_nc:
        issues.warning('Ventas', f'{len(pending_nc)} nota(s) de crédito del mes NO están autorizadas y no se incluyen: ' + ', '.join(n.voucher_number_full for n in pending_nc[:8]))
    for note in credit_notes:
        if note.status not in AUTHORIZED:
            continue
        _add_sale_row(data, note.sale.client, VOUCHER_TYPE[1][0], note.receipt.establishment_code, note.subtotal_0, note.subtotal_12, note.total_iva, note.sale.payment_method, issues, f'Nota de crédito {note.voucher_number_full}', count=1)

    # ---- retenciones que los clientes practicaron (se suman a la fila del cliente)
    for retention in Retention.objects.filter(issue_date__range=(first, last)).select_related('sale__client__user', 'sale__receipt'):
        sale = retention.sale
        key, row = _sale_row(data, sale.client, VOUCHER_TYPE[0][0], sale.receipt.establishment_code, issues, f'Retención {retention.document_number}')
        row['valorRetIva'] += money(retention.iva_retained)
        row['valorRetRenta'] += money(retention.income_tax_retained)

    # ---- no incluidos
    for voucher, label in ((VOUCHER_TYPE[4][0], 'liquidación(es) de compra'),):
        count = Sale.objects.filter(date_joined__range=(first, last), receipt__voucher_type=voucher).exclude(status=CANCELED).count()
        if count:
            issues.warning('Compras', f'Hay {count} {label} en el mes: el sistema todavía NO las incluye en el ATS (van en compras con tipo 03). Agrégalas a mano si corresponde.')
    tickets = Sale.objects.filter(date_joined__range=(first, last), receipt__voucher_type=VOUCHER_TYPE[2][0]).exclude(status=CANCELED).count()
    if tickets:
        issues.warning('Ventas', f'Hay {tickets} ticket(s) de venta en el mes: no son comprobantes autorizados por el SRI y no se reportan en el ATS (si el negocio los usa, el contador debe revisar cómo declararlos).')

    # ---- anulados (facturas anuladas sin nota de crédito: su secuencial ya se consumió)
    canceled = Sale.objects.filter(date_joined__range=(first, last), receipt__voucher_type=VOUCHER_TYPE[0][0], status=CANCELED, creditnote__isnull=True).select_related('receipt').order_by('receipt__establishment_code', 'receipt__issuing_point_code', 'voucher_number')
    for sale in canceled:
        doc = f'Factura anulada {sale.voucher_number_full}'
        access = (sale.access_code or '').strip()
        if not (access.isdigit() and 3 <= len(access) <= 49):
            issues.warning(doc, 'No tiene número de autorización (clave de acceso): no se reporta como anulada porque nunca existió ante el SRI.')
            continue
        data['canceled'].append({
            'tipoComprobante': VOUCHER_TYPE[0][0], 'establecimiento': sale.receipt.establishment_code,
            'puntoEmision': sale.receipt.issuing_point_code, 'secuencial': int(sale.voucher_number), 'autorizacion': access,
        })

    # ---- establecimientos (todos los que tienen serie de factura / nota de crédito)
    codes = sorted(set(Receipt.objects.filter(voucher_type__in=(VOUCHER_TYPE[0][0], VOUCHER_TYPE[1][0])).values_list('establishment_code', flat=True)))
    if not codes:
        codes = [company.establishment_code]
    for code in codes:
        data['establishments'].setdefault(code, {'ventasEstab': ZERO})
    for row in data['sales'].values():
        if row['tipoComprobante'] == VOUCHER_TYPE[0][0]:
            sign = 1
        else:
            sign = -1
        base = row['baseNoGraIva'] + row['baseImponible'] + row['baseImpGrav']
        data['establishments'].setdefault(row['_estab'], {'ventasEstab': ZERO})
        data['establishments'][row['_estab']]['ventasEstab'] += sign * base
    data['num_establishments'] = len(data['establishments'])
    issues.info('Encabezado', f'El anexo declara {data["num_establishments"]} establecimiento(s) ({", ".join(data["establishments"])}). Debe coincidir con los establecimientos ACTIVOS inscritos en el RUC.')

    data['total_sales'] = sum((v['ventasEstab'] for v in data['establishments'].values()), ZERO)
    data['stats'].update({
        'sale_rows': len(data['sales']),
        'invoices': sum(r['numeroComprobantes'] for r in data['sales'].values() if r['tipoComprobante'] == VOUCHER_TYPE[0][0]),
        'credit_notes': sum(r['numeroComprobantes'] for r in data['sales'].values() if r['tipoComprobante'] == VOUCHER_TYPE[1][0]),
        'canceled': len(data['canceled']),
    })
    data['issues'] = issues
    return data


def _purchase_record(company, purchase, retentions, issues, doc):
    parts = split_number(purchase.number)
    if parts is None:
        issues.error(doc, f'El número "{purchase.number}" debe ser el de la factura del proveedor: 15 dígitos (establecimiento + punto + secuencial).')
        return None
    establishment, point, sequence = parts
    provider = purchase.provider
    id_type, id_number = _id_type_purchase(provider, issues, doc)

    registered = purchase.date_joined.astimezone().date() if getattr(purchase.date_joined, 'tzinfo', None) else purchase.date_joined.date()
    issued = purchase.issue_date or registered
    if issued > registered:
        issues.error(doc, f'La fecha de emisión del comprobante ({date_text(issued)}) no puede ser posterior a su fecha de registro ({date_text(registered)}).')

    authorization = (purchase.authorization_number or '').strip()
    if not authorization:
        if purchase.voucher_type in NO_AUTHORIZATION_TYPES:
            authorization = '9999999999'
        else:
            issues.error(doc, 'Falta el número de autorización del comprobante del proveedor (Compras > editar la compra).')
    elif not authorization.isdigit() or len(authorization) not in (10, 37, 49):
        issues.warning(doc, f'El número de autorización "{authorization}" no tiene 10, 37 o 49 dígitos.')

    bases = {
        'baseNoGraIva': money(purchase.subtotal_no_object), 'baseImponible': money(purchase.subtotal_0),
        'baseImpGrav': money(purchase.subtotal_iva), 'baseImpExe': money(purchase.subtotal_exempt),
    }
    if bases['baseNoGraIva'] + bases['baseImponible'] + bases['baseImpGrav'] <= 0:
        # Compras antiguas (sin desglose de IVA): todo el subtotal va como tarifa 0%.
        if purchase.subtotal and bases['baseImpExe'] <= 0:
            bases['baseImponible'] = money(purchase.subtotal)
            issues.warning(doc, 'La compra no tiene desglose de IVA (es anterior a esa función): se reportó el subtotal como tarifa 0%.')
        elif bases['baseImpExe'] <= 0:
            issues.error(doc, 'La compra no tiene valores (base 0%, con IVA o no objeto de IVA).')
    if not purchase.tax_support:
        issues.error(doc, 'Falta el sustento tributario de la compra.')

    iva = money(purchase.total_iva)
    total_taxable = sum(bases.values(), ZERO) + iva
    record = {
        'doc': doc, 'codSustento': purchase.tax_support or '', 'tpIdProv': id_type, 'idProv': id_number,
        'tipoComprobante': purchase.voucher_type, 'parteRel': 'SI' if provider.related_party else 'NO',
        'fechaRegistro': registered, 'establecimiento': establishment, 'puntoEmision': point, 'secuencial': sequence,
        'fechaEmision': issued, 'autorizacion': authorization, 'montoIce': ZERO, 'montoIva': iva,
        'pagoLocExt': '01',
        'formasDePago': [purchase.payment_method] if (total_taxable > PAYMENT_METHOD_THRESHOLD and purchase.payment_method) else [],
        'retenciones': {name: ZERO for name in IVA_RETENTION_FIELDS.values()},
        'air': [], 'ret_doc': None,
    }
    record.update(bases)
    if id_type == '03':
        record['tipoProv'] = '01'
        record['denoProv'] = clean_name(provider.name) or None

    authorized = [r for r in retentions if r.status in AUTHORIZED]
    for retention in retentions:
        if retention.status not in AUTHORIZED:
            issues.warning(doc, f'La retención {retention.voucher_number_full} aún no está autorizada por el SRI: no se incluye. Autorízala antes de presentar el anexo.')
    if len(authorized) > 1:
        issues.warning(doc, 'La compra tiene más de una retención autorizada: el ATS admite un solo comprobante de retención por compra; se reporta el primero y se suman los valores de todas.')
    for retention in authorized:
        for detail in retention.supplierretentiondetail_set.all():
            if detail.concept.kind == RETENTION_KIND[1][0]:
                field = IVA_RETENTION_FIELDS.get(int(Decimal(detail.percentage)))
                if field:
                    record['retenciones'][field] += money(detail.value)
                else:
                    issues.warning(doc, f'Retención de IVA al {detail.percentage}%: el ATS solo admite 10, 20, 30, 50, 70 o 100%.')
            else:
                record['air'].append({'codRetAir': detail.concept.code, 'baseImpAir': money(detail.base), 'porcentajeAir': money(detail.percentage), 'valRetAir': money(detail.value)})
    if authorized:
        first = authorized[0]
        e, p, s = first.voucher_number_full.split('-')
        record['ret_doc'] = {
            'estab': e, 'pto': p, 'sec': int(s), 'aut': first.access_code or '',
            'fecha': first.date_joined.astimezone().date() if getattr(first.date_joined, 'tzinfo', None) else first.date_joined.date(),
        }
        if not first.access_code:
            issues.error(doc, f'La retención {first.voucher_number_full} no tiene número de autorización.')
        elif record['ret_doc']['fecha'] < registered:
            issues.error(doc, 'La fecha de emisión de la retención no puede ser anterior a la fecha de registro de la compra.')
    if not record['air']:
        # Compra sin retención de renta: el concepto 332 (otras compras no sujetas a retención).
        record['air'].append({'codRetAir': '332', 'baseImpAir': sum(bases.values(), ZERO), 'porcentajeAir': ZERO, 'valRetAir': ZERO})
    return record


def _sale_row(data, client, voucher, establishment, issues, doc):
    id_type, id_number = _id_type_sale(client, issues, doc)
    key = (id_type, id_number, voucher)
    row = data['sales'].get(key)
    if row is None:
        row = {
            'tpIdCliente': id_type, 'idCliente': id_number, 'tipoComprobante': voucher, 'tipoEmision': 'E',
            'numeroComprobantes': 0, 'baseNoGraIva': ZERO, 'baseImponible': ZERO, 'baseImpGrav': ZERO, 'montoIva': ZERO,
            'valorRetIva': ZERO, 'valorRetRenta': ZERO, 'formasDePago': [], '_estab': establishment,
        }
        if id_type in ('04', '05', '06'):
            row['parteRelVtas'] = 'NO'
        if id_type == '06':
            row['tipoCliente'] = '01'
            row['denoCli'] = clean_name(client.user.names) or None
        data['sales'][key] = row
    return key, row


def _add_sale_row(data, client, voucher, establishment, base_0, base_iva, iva, payment_method, issues, doc, count):
    key, row = _sale_row(data, client, voucher, establishment, issues, doc)
    row['numeroComprobantes'] += count
    row['baseImponible'] += money(base_0)
    row['baseImpGrav'] += money(base_iva)
    row['montoIva'] += money(iva)
    if payment_method and payment_method not in row['formasDePago']:
        row['formasDePago'].append(payment_method)


# --------------------------------------------------------------------------- XML
def _sub(parent, tag, text=None):
    node = etree.SubElement(parent, tag)
    if text is not None:
        node.text = str(text)
    return node


def render_xml(data):
    """XML del ATS (str) con el orden de elementos que exige el esquema."""
    root = etree.Element('iva')
    _sub(root, 'TipoIDInformante', 'R')
    _sub(root, 'IdInformante', data['ruc'])
    _sub(root, 'razonSocial', data['name'])
    _sub(root, 'Anio', data['year'])
    _sub(root, 'Mes', f'{data["month"]:02d}')
    _sub(root, 'numEstabRuc', f'{data["num_establishments"]:03d}')
    _sub(root, 'totalVentas', fmt(data['total_sales']))
    _sub(root, 'codigoOperativo', 'IVA')

    purchases = _sub(root, 'compras')
    for p in data['purchases']:
        node = _sub(purchases, 'detalleCompras')
        _sub(node, 'codSustento', p['codSustento'])
        _sub(node, 'tpIdProv', p['tpIdProv'])
        _sub(node, 'idProv', p['idProv'])
        _sub(node, 'tipoComprobante', p['tipoComprobante'])
        if p.get('tipoProv'):
            _sub(node, 'tipoProv', p['tipoProv'])
        if p.get('denoProv'):
            _sub(node, 'denoProv', p['denoProv'])
        _sub(node, 'parteRel', p['parteRel'])
        _sub(node, 'fechaRegistro', date_text(p['fechaRegistro']))
        _sub(node, 'establecimiento', p['establecimiento'])
        _sub(node, 'puntoEmision', p['puntoEmision'])
        _sub(node, 'secuencial', p['secuencial'])
        _sub(node, 'fechaEmision', date_text(p['fechaEmision']))
        _sub(node, 'autorizacion', p['autorizacion'])
        for tag in ('baseNoGraIva', 'baseImponible', 'baseImpGrav', 'baseImpExe', 'montoIce', 'montoIva'):
            _sub(node, tag, fmt(p[tag]))
        # El esquema exige este orden: 10, 20, 30, 50, 70, 100.
        for field in IVA_RETENTION_FIELDS.values():
            _sub(node, field, fmt(p['retenciones'][field]))
        pay = _sub(node, 'pagoExterior')
        _sub(pay, 'pagoLocExt', p['pagoLocExt'])
        _sub(pay, 'paisEfecPago', 'NA')
        _sub(pay, 'aplicConvDobTrib', 'NA')
        _sub(pay, 'pagExtSujRetNorLeg', 'NA')
        if p['formasDePago']:
            forms = _sub(node, 'formasDePago')
            for code in p['formasDePago']:
                _sub(forms, 'formaPago', code)
        air = _sub(node, 'air')
        for a in p['air']:
            detail = _sub(air, 'detalleAir')
            _sub(detail, 'codRetAir', a['codRetAir'])
            _sub(detail, 'baseImpAir', fmt(a['baseImpAir']))
            _sub(detail, 'porcentajeAir', fmt(a['porcentajeAir']))
            _sub(detail, 'valRetAir', fmt(a['valRetAir']))
        if p['ret_doc']:
            r = p['ret_doc']
            _sub(node, 'estabRetencion1', r['estab'])
            _sub(node, 'ptoEmiRetencion1', r['pto'])
            _sub(node, 'secRetencion1', r['sec'])
            _sub(node, 'autRetencion1', r['aut'])
            _sub(node, 'fechaEmiRet1', date_text(r['fecha']))

    sales = _sub(root, 'ventas')
    for row in data['sales'].values():
        node = _sub(sales, 'detalleVentas')
        _sub(node, 'tpIdCliente', row['tpIdCliente'])
        _sub(node, 'idCliente', row['idCliente'])
        if row.get('parteRelVtas'):
            _sub(node, 'parteRelVtas', row['parteRelVtas'])
        if row.get('tipoCliente'):
            _sub(node, 'tipoCliente', row['tipoCliente'])
        if row.get('denoCli'):
            _sub(node, 'denoCli', row['denoCli'])
        _sub(node, 'tipoComprobante', row['tipoComprobante'])
        _sub(node, 'tipoEmision', row['tipoEmision'])
        _sub(node, 'numeroComprobantes', row['numeroComprobantes'])
        for tag in ('baseNoGraIva', 'baseImponible', 'baseImpGrav', 'montoIva'):
            _sub(node, tag, fmt(row[tag]))
        _sub(node, 'valorRetIva', fmt(row['valorRetIva']))
        _sub(node, 'valorRetRenta', fmt(row['valorRetRenta']))
        if row['formasDePago']:
            forms = _sub(node, 'formasDePago')
            for code in row['formasDePago']:
                _sub(forms, 'formaPago', code)

    establishments = _sub(root, 'ventasEstablecimiento')
    for code, values in data['establishments'].items():
        node = _sub(establishments, 'ventaEst')
        _sub(node, 'codEstab', code)
        _sub(node, 'ventasEstab', fmt(values['ventasEstab']))
        _sub(node, 'ivaComp', fmt(ZERO))

    if data['canceled']:
        canceled = _sub(root, 'anulados')
        for c in data['canceled']:
            node = _sub(canceled, 'detalleAnulados')
            _sub(node, 'tipoComprobante', c['tipoComprobante'])
            _sub(node, 'establecimiento', c['establecimiento'])
            _sub(node, 'puntoEmision', c['puntoEmision'])
            _sub(node, 'secuencialInicio', c['secuencial'])
            _sub(node, 'secuencialFin', c['secuencial'])
            _sub(node, 'autorizacion', c['autorizacion'])

    return etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=True).decode('utf-8')


def validate_xml(xml):
    """Lista de errores (str) contra el esquema oficial ats.xsd; vacía si cumple."""
    global _schema
    if _schema is None:
        import os
        _schema = etree.XMLSchema(etree.parse(os.path.join(XSD_DIR, 'ats.xsd')))
    document = etree.fromstring(xml.encode('utf-8'))
    if _schema.validate(document):
        return []
    return [f'línea {e.line}: {e.message}' for e in list(_schema.error_log)[:10]]


# ------------------------------------------------------------------- resultado
def build_month(company, year, month):
    """Datos + XML + validación + resumen de un mes."""
    data = collect_month(company, year, month)
    xml = render_xml(data)
    xsd_errors = validate_xml(xml)
    issues = data['issues']
    p_total = sum((p['baseNoGraIva'] + p['baseImponible'] + p['baseImpGrav'] + p['baseImpExe'] for p in data['purchases']), ZERO)
    p_iva = sum((p['montoIva'] for p in data['purchases']), ZERO)
    summary = {
        'year': year, 'month': month, 'label': month_label(year, month), 'file': zip_name(year, month) + '.zip',
        'purchases': data['stats']['purchases'], 'purchases_base': float(p_total), 'purchases_iva': float(p_iva),
        'sale_rows': data['stats']['sale_rows'], 'invoices': data['stats']['invoices'],
        'credit_notes': data['stats']['credit_notes'], 'canceled': data['stats']['canceled'],
        'total_sales': float(data['total_sales']),
        'issues': issues.items, 'errors': sum(1 for i in issues.items if i['level'] == 'error'),
        'warnings': sum(1 for i in issues.items if i['level'] == 'warning'),
        'xsd_errors': xsd_errors, 'valid': not xsd_errors and not issues.has_errors,
    }
    return xml, summary


def monthly_zip(year, month, xml):
    """ATmmaaaa.zip con ATmmaaaa.xml dentro (el nombre que exige el SRI)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zip_name(year, month) + '.xml', xml.encode('utf-8'))
    return buffer.getvalue()


def bundle_zip(files):
    """Un ZIP con varios ATmmaaaa.zip (uno por mes) para bajarlos juntos."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files:
            archive.writestr(name, content)
    return buffer.getvalue()

"""
Parseo del XML de un comprobante de retención electrónico (el que el cliente
entrega cuando retiene IVA y/o Renta sobre una factura nuestra).

Sigue el esquema estándar del SRI para comprobantes de retención:
<comprobanteRetencion><infoTributaria>...<infoCompRetencion>...<impuestos>
<impuesto>...codigo(1=RENTA, 2=IVA)...baseImponible...porcentajeRetener...
valRetenido...</impuesto></impuestos></comprobanteRetencion>.

Igual que con las facturas de compra (ver purchase_xml_import.py), el XML
"autorizado" que de verdad circula viene envuelto en <autorizacion>...
<comprobante><![CDATA[<comprobanteRetencion ...>...]]></comprobante>
</autorizacion>. Este módulo acepta tanto ese envoltorio como un
<comprobanteRetencion> "pelado".
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree


class InvalidRetentionXMLError(ValueError):
    """El XML no se pudo leer o no tiene la forma de un comprobante de retención."""
    pass


def _parse_xml_bytes(raw_xml, error_message):
    try:
        return ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        raise InvalidRetentionXMLError(error_message)


def _extract_retention_root(raw_xml):
    if not raw_xml or not raw_xml.strip():
        raise InvalidRetentionXMLError('El archivo XML está vacío.')

    root = _parse_xml_bytes(raw_xml, 'El archivo seleccionado no es un XML válido.')

    if root.tag == 'autorizacion':
        comprobante = root.find('comprobante')
        if comprobante is None or not (comprobante.text or '').strip():
            raise InvalidRetentionXMLError('El XML de autorización no contiene un comprobante embebido.')
        root = _parse_xml_bytes(
            comprobante.text.strip().encode('utf-8'),
            'El comprobante embebido en el XML de autorización no es válido.'
        )

    if root.tag != 'comprobanteRetencion':
        raise InvalidRetentionXMLError('El XML no corresponde a un comprobante de retención del SRI (se esperaba un comprobante tipo "comprobanteRetencion").')

    return root


def _text(element, tag):
    node = element.find(tag)
    if node is None or node.text is None:
        return ''
    return node.text.strip()


def _to_decimal(value, field_description):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        raise InvalidRetentionXMLError(f'El valor de {field_description} en el XML no es un número válido: "{value}"')


def parse_retention_xml(raw_xml):
    """
    raw_xml: contenido crudo (bytes) del archivo XML subido.

    Devuelve {'info': {...datos del agente de retención y del comprobante...},
    'iva_retained': Decimal, 'income_tax_retained': Decimal, 'total_retained': Decimal}
    o lanza InvalidRetentionXMLError con un mensaje claro en español.
    """
    if isinstance(raw_xml, str):
        raw_xml = raw_xml.encode('utf-8')

    root = _extract_retention_root(raw_xml)

    info_tributaria = root.find('infoTributaria')
    info_comp_retencion = root.find('infoCompRetencion')
    impuestos = root.find('impuestos')
    if info_tributaria is None or info_comp_retencion is None or impuestos is None:
        raise InvalidRetentionXMLError('El XML no tiene la estructura esperada de un comprobante de retención del SRI (falta infoTributaria, infoCompRetencion o impuestos).')

    impuesto_nodes = impuestos.findall('impuesto')
    if not impuesto_nodes:
        raise InvalidRetentionXMLError('El XML no contiene ningún impuesto retenido.')

    iva_retained = Decimal('0.00')
    income_tax_retained = Decimal('0.00')
    for index, impuesto in enumerate(impuesto_nodes, start=1):
        codigo = _text(impuesto, 'codigo')
        valor_raw = _text(impuesto, 'valorRetenido') or _text(impuesto, 'valRetenido')
        if not codigo:
            raise InvalidRetentionXMLError(f'El impuesto {index} del XML no tiene código (1=Renta, 2=IVA).')
        if not valor_raw:
            raise InvalidRetentionXMLError(f'El impuesto {index} del XML no tiene valor retenido.')
        valor_decimal = _to_decimal(valor_raw, f'el valor retenido del impuesto {index}')
        if valor_decimal < 0:
            raise InvalidRetentionXMLError(f'El valor retenido del impuesto {index} no puede ser negativo.')
        if codigo == '2':
            iva_retained += valor_decimal
        elif codigo == '1':
            income_tax_retained += valor_decimal
        else:
            raise InvalidRetentionXMLError(f'El impuesto {index} del XML tiene un código desconocido ("{codigo}"); se esperaba 1 (Renta) o 2 (IVA).')

    estab = _text(info_tributaria, 'estab')
    pto_emi = _text(info_tributaria, 'ptoEmi')
    secuencial = _text(info_tributaria, 'secuencial')
    document_number = f'{estab}-{pto_emi}-{secuencial}' if estab and pto_emi and secuencial else ''

    fecha_emision_raw = _text(info_comp_retencion, 'fechaEmision')
    num_doc_sustento = _text(info_comp_retencion, 'numDocSustento')

    info = {
        'ruc': _text(info_tributaria, 'ruc'),
        'razon_social': _text(info_tributaria, 'razonSocial'),
        'clave_acceso': _text(info_tributaria, 'claveAcceso'),
        'document_number': document_number,
        'issue_date_raw': fecha_emision_raw,
        # numDocSustento suele venir sin guiones (ej. "001001000000251"): se usa
        # solo para sugerir/validar contra la factura, no se parte a la fuerza.
        'supported_document_number': num_doc_sustento,
    }

    iva_retained = iva_retained.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    income_tax_retained = income_tax_retained.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        'info': info,
        'iva_retained': iva_retained,
        'income_tax_retained': income_tax_retained,
        'total_retained': iva_retained + income_tax_retained,
    }

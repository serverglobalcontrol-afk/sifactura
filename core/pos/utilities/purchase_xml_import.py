"""
Lectura y VALIDACIÓN del XML de una factura de compra (la factura electrónica
que un proveedor entrega, en formato PDF + XML, cuando le compramos).

El XML que emite este mismo sistema para SUS ventas (ver
core/pos/models.py Sale.generate_xml) sigue el esquema estándar del SRI para
facturas electrónicas ecuatorianas: <factura><detalles><detalle>... Todo
negocio ecuatoriano usa ese mismo esquema, así que el XML que llega de un
proveedor tiene la misma forma.

El XML "autorizado" que de verdad circula entre negocios normalmente viene
envuelto así:

    <autorizacion>
        <estado>AUTORIZADO</estado>
        <numeroAutorizacion>...</numeroAutorizacion>
        <fechaAutorizacion>...</fechaAutorizacion>
        <ambiente>PRODUCCION</ambiente>
        <comprobante><![CDATA[<factura id="comprobante" version="1.0.0">...</factura>]]></comprobante>
    </autorizacion>

Este módulo acepta tanto ese envoltorio como un <factura> "pelado".

Como esos datos quedan registrados como historial de la compra (y alimentan el
ATS), además de leerlos se validan: un XML alterado, incompleto o que no
corresponde a una factura real se rechaza con un mensaje claro en vez de
guardarse.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree

CENT = Decimal('0.01')
# Diferencia tolerada (en dólares) entre lo que declara el XML y lo recalculado:
# el XML trae precios con hasta 6 decimales y el sistema guarda 2.
TOTALS_TOLERANCE_PER_LINE = Decimal('0.02')


class InvalidPurchaseXMLError(ValueError):
    """El XML no se pudo leer, no tiene la forma de una factura del SRI o sus datos no son consistentes."""
    pass


def _parse_xml_bytes(raw_xml, error_message):
    try:
        return ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        raise InvalidPurchaseXMLError(error_message)


def _text(element, tag):
    node = element.find(tag) if element is not None else None
    if node is None or node.text is None:
        return ''
    return node.text.strip()


def _extract_factura_root(raw_xml):
    """Devuelve (raíz <factura>, datos de la autorización si venía envuelto)."""
    if not raw_xml or not raw_xml.strip():
        raise InvalidPurchaseXMLError('El archivo XML está vacío.')

    root = _parse_xml_bytes(raw_xml, 'El archivo seleccionado no es un XML válido.')
    authorization = {}

    if root.tag == 'autorizacion':
        authorization = {
            'estado': _text(root, 'estado').upper(),
            'numero_autorizacion': _text(root, 'numeroAutorizacion'),
            'fecha_autorizacion': _text(root, 'fechaAutorizacion'),
            'ambiente': _text(root, 'ambiente').upper(),
        }
        comprobante = root.find('comprobante')
        if comprobante is None or not (comprobante.text or '').strip():
            raise InvalidPurchaseXMLError('El XML de autorización no contiene un comprobante embebido.')
        # El SRI solo entrega el comprobante dentro de una autorización cuando
        # ya lo autorizó; cualquier otro estado no es una factura válida.
        if authorization['estado'] and authorization['estado'] != 'AUTORIZADO':
            raise InvalidPurchaseXMLError(f'El comprobante no está autorizado por el SRI (estado: {authorization["estado"]}).')
        root = _parse_xml_bytes(
            comprobante.text.strip().encode('utf-8'),
            'El comprobante embebido en el XML de autorización no es válido.'
        )

    if root.tag != 'factura':
        raise InvalidPurchaseXMLError('El XML no corresponde a una factura electrónica del SRI (se esperaba un comprobante tipo "factura").')

    return root, authorization


def _to_decimal(value, field_description):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        raise InvalidPurchaseXMLError(f'El valor de {field_description} en el XML no es un número válido: "{value}"')


def _money(value, field_description, default=None):
    if (value is None or value == '') and default is not None:
        return default
    return _to_decimal(value, field_description).quantize(CENT, rounding=ROUND_HALF_UP)


def _iso_date(ddmmyyyy):
    """dd/mm/aaaa (formato del SRI) -> aaaa-mm-dd; '' si no se puede leer."""
    try:
        return datetime.strptime(ddmmyyyy, '%d/%m/%Y').strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return ''


def _line_tax(detalle, index):
    """(tipo, tarifa) del IVA de una línea: 'iva' (con su tarifa), '0',
    'no_objeto' o 'exento'. Se ignoran otros impuestos (ICE, IRBPNR)."""
    impuestos = detalle.find('impuestos')
    if impuestos is not None:
        for impuesto in impuestos.findall('impuesto'):
            if _text(impuesto, 'codigo') != '2':
                continue
            codigo_porcentaje = _text(impuesto, 'codigoPorcentaje')
            tarifa = _money(_text(impuesto, 'tarifa'), f'la tarifa de IVA de la línea {index}', default=Decimal('0.00'))
            if codigo_porcentaje == '6':
                return 'no_objeto', Decimal('0.00')
            if codigo_porcentaje == '7':
                return 'exento', Decimal('0.00')
            if tarifa == 0:
                return '0', Decimal('0.00')
            return 'iva', tarifa
    # Sin impuesto de IVA en la línea: se trata como tarifa 0 %.
    return '0', Decimal('0.00')


def validate_access_key(key, ruc, cod_doc, estab, pto_emi, secuencial, issue_date_iso):
    """Valida la clave de acceso de 49 dígitos del comprobante: largo, dígito
    verificador (módulo 11), y que coincida con los datos del propio XML."""
    from core.pos.utilities.sri import SRI

    if not key:
        raise InvalidPurchaseXMLError('El XML no trae la clave de acceso (claveAcceso): no se puede verificar que sea una factura real.')
    if not key.isdigit() or len(key) != 49:
        raise InvalidPurchaseXMLError(f'La clave de acceso debe tener 49 dígitos (tiene {len(key)}).')
    if SRI().compute_mod11(key[:48]) != key[48]:
        raise InvalidPurchaseXMLError('La clave de acceso del XML no es válida (el dígito verificador no coincide): el archivo pudo haber sido alterado.')
    if key[8:10] != '01' or (cod_doc and cod_doc != '01'):
        raise InvalidPurchaseXMLError('El comprobante no es una factura (código de documento distinto de 01).')
    if ruc and key[10:23] != ruc:
        raise InvalidPurchaseXMLError('El RUC dentro de la clave de acceso no coincide con el RUC del emisor del XML.')
    if estab and pto_emi and secuencial and key[24:39] != f'{estab}{pto_emi}{secuencial}':
        raise InvalidPurchaseXMLError('El número de factura del XML no coincide con el de su clave de acceso.')
    if issue_date_iso:
        key_date = f'{key[4:8]}-{key[2:4]}-{key[0:2]}'
        if key_date != issue_date_iso:
            raise InvalidPurchaseXMLError('La fecha de emisión del XML no coincide con la de su clave de acceso.')


def parse_supplier_invoice_xml(raw_xml):
    """
    raw_xml: contenido crudo (bytes) del archivo XML subido.

    Devuelve {'info': {...emisor, comprobante, autorización, totales...},
              'lines': [{'code', 'description', 'cant', 'price', 'tax', 'iva_percent', 'subtotal'}, ...],
              'warnings': [...avisos que no impiden registrar la compra...]}
    o lanza InvalidPurchaseXMLError con un mensaje claro en español.
    """
    if isinstance(raw_xml, str):
        raw_xml = raw_xml.encode('utf-8')

    root, authorization = _extract_factura_root(raw_xml)

    info_tributaria = root.find('infoTributaria')
    info_factura = root.find('infoFactura')
    detalles = root.find('detalles')
    if info_tributaria is None or detalles is None:
        raise InvalidPurchaseXMLError('El XML no tiene la estructura esperada de una factura electrónica del SRI (falta infoTributaria o detalles).')

    detalle_nodes = detalles.findall('detalle')
    if not detalle_nodes:
        raise InvalidPurchaseXMLError('El XML no contiene ningún producto (detalle) para importar.')

    warnings = []
    lines = []
    for index, detalle in enumerate(detalle_nodes, start=1):
        code = _text(detalle, 'codigoPrincipal') or _text(detalle, 'codigoAuxiliar')
        description = _text(detalle, 'descripcion')
        cantidad_raw = _text(detalle, 'cantidad')
        precio_raw = _text(detalle, 'precioUnitario')

        if not code:
            raise InvalidPurchaseXMLError(f'La línea {index} del XML no tiene código de producto (codigoPrincipal).')
        if not description:
            raise InvalidPurchaseXMLError(f'La línea {index} del XML no tiene descripción.')
        if not cantidad_raw:
            raise InvalidPurchaseXMLError(f'La línea {index} ({description}) no tiene cantidad.')
        if not precio_raw:
            raise InvalidPurchaseXMLError(f'La línea {index} ({description}) no tiene precio unitario.')

        cant_decimal = _to_decimal(cantidad_raw, f'la cantidad de la línea {index}')
        price_decimal = _to_decimal(precio_raw, f'el precio unitario de la línea {index}')

        if cant_decimal <= 0:
            raise InvalidPurchaseXMLError(f'La cantidad de la línea {index} ({description}) debe ser mayor a cero.')
        if price_decimal < 0:
            raise InvalidPurchaseXMLError(f'El precio unitario de la línea {index} ({description}) no puede ser negativo.')
        if cant_decimal != cant_decimal.to_integral_value():
            warnings.append(f'La línea {index} ({description}) tiene cantidad decimal ({cant_decimal}): el sistema la redondea a {int(cant_decimal.to_integral_value(rounding=ROUND_HALF_UP))}.')

        cant = int(cant_decimal.to_integral_value(rounding=ROUND_HALF_UP))
        line_total = _money(_text(detalle, 'precioTotalSinImpuesto'), f'el total de la línea {index}', default=(cant_decimal * price_decimal).quantize(CENT, rounding=ROUND_HALF_UP))
        discount = _money(_text(detalle, 'descuento'), f'el descuento de la línea {index}', default=Decimal('0.00'))
        price = price_decimal.quantize(CENT, rounding=ROUND_HALF_UP)
        if discount > 0:
            # precioUnitario es ANTES de descuento: se registra el precio neto
            # para que el subtotal de la línea coincida con el de la factura.
            price = (line_total / cant_decimal).quantize(CENT, rounding=ROUND_HALF_UP)
            warnings.append(f'La línea {index} ({description}) trae descuento de ${discount}: se registra el precio neto ${price}.')
        tax, iva_percent = _line_tax(detalle, index)

        lines.append({
            'code': code,
            'description': description,
            'cant': cant,
            'price': price,
            'tax': tax,
            'iva_percent': iva_percent,
            'subtotal': line_total,
        })

    estab = _text(info_tributaria, 'estab')
    pto_emi = _text(info_tributaria, 'ptoEmi')
    secuencial = _text(info_tributaria, 'secuencial')
    ruc = _text(info_tributaria, 'ruc')
    # Concatenado en dígitos (sin guiones): el campo "Número de factura" de
    # Compras solo acepta dígitos. Se incluyen establecimiento y punto de
    # emisión (no solo el secuencial) porque el secuencial se reinicia por
    # cada uno; usar solo el secuencial podría chocar entre proveedores.
    invoice_number = f'{estab}{pto_emi}{secuencial}' if estab and pto_emi and secuencial else ''
    access_key = _text(info_tributaria, 'claveAcceso')
    issue_date = _iso_date(_text(info_factura, 'fechaEmision'))

    validate_access_key(access_key, ruc, _text(info_tributaria, 'codDoc'), estab, pto_emi, secuencial, issue_date)

    # --- totales declarados vs recalculados desde las líneas
    declared_subtotal = _money(_text(info_factura, 'totalSinImpuestos'), 'el total sin impuestos', default=None) if _text(info_factura, 'totalSinImpuestos') else None
    declared_total = _money(_text(info_factura, 'importeTotal'), 'el importe total', default=None) if _text(info_factura, 'importeTotal') else None
    declared_iva = Decimal('0.00')
    tax_node = info_factura.find('totalConImpuestos') if info_factura is not None else None
    if tax_node is not None:
        for total_impuesto in tax_node.findall('totalImpuesto'):
            if _text(total_impuesto, 'codigo') == '2':
                declared_iva += _money(_text(total_impuesto, 'valor'), 'el IVA declarado', default=Decimal('0.00'))
    lines_subtotal = sum((l['subtotal'] for l in lines), Decimal('0.00'))
    tolerance = TOTALS_TOLERANCE_PER_LINE * len(lines) + CENT
    if declared_subtotal is not None and abs(lines_subtotal - declared_subtotal) > tolerance:
        raise InvalidPurchaseXMLError(f'El XML es inconsistente: la suma de sus líneas (${lines_subtotal}) no coincide con el total sin impuestos que declara (${declared_subtotal}).')
    if declared_total is not None and declared_subtotal is not None:
        propina = _money(_text(info_factura, 'propina'), 'la propina', default=Decimal('0.00'))
        if abs(declared_subtotal + declared_iva + propina - declared_total) > tolerance:
            raise InvalidPurchaseXMLError(f'El XML es inconsistente: total sin impuestos (${declared_subtotal}) + IVA (${declared_iva}) no suman el importe total (${declared_total}).')

    if authorization.get('ambiente') == 'PRUEBAS' or _text(info_tributaria, 'ambiente') == '1':
        warnings.append('El XML fue emitido en ambiente de PRUEBAS del SRI: no es una factura real y no sirve como sustento tributario.')

    info = {
        'ruc': ruc,
        'razon_social': _text(info_tributaria, 'razonSocial'),
        'clave_acceso': access_key,
        'estab': estab,
        'pto_emi': pto_emi,
        'secuencial': secuencial,
        'invoice_number': invoice_number,
        'issue_date': issue_date,
        'authorization_number': authorization.get('numero_autorizacion') or access_key,
        'authorization_date': authorization.get('fecha_autorizacion', ''),
        'authorized': bool(authorization) and authorization.get('estado') == 'AUTORIZADO',
        'total_without_tax': float(declared_subtotal if declared_subtotal is not None else lines_subtotal),
        'total_iva': float(declared_iva),
        'total': float(declared_total) if declared_total is not None else None,
    }

    return {'info': info, 'lines': lines, 'warnings': warnings}

"""
Parseo del XML de una factura de compra (la factura electrónica que un
proveedor entrega, en formato PDF + XML, cuando le compramos mercadería).

El XML que emite este mismo sistema para SUS ventas (ver
core/pos/models.py Sale.generate_xml) sigue el esquema estándar del SRI
para facturas electrónicas ecuatorianas: <factura><detalles><detalle>...
Como todo negocio ecuatoriano usa ese mismo esquema, el XML que llega de
un proveedor tiene la misma forma, y por eso se puede reutilizar el
conocimiento de esas etiquetas (infoTributaria, detalles/detalle,
codigoPrincipal, descripcion, cantidad, precioUnitario, etc.) para leerlo.

El XML "autorizado" que de verdad circula entre negocios (el que el SRI
entrega y que este mismo sistema genera en Sale.generate_xml -> SRI().
authorize_xml) normalmente viene envuelto así:

    <autorizacion>
        <estado>AUTORIZADO</estado>
        ...
        <comprobante><![CDATA[<factura id="comprobante" version="1.0.0">...</factura>]]></comprobante>
    </autorizacion>

Este módulo acepta tanto ese envoltorio como un <factura> "pelado".
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree


class InvalidPurchaseXMLError(ValueError):
    """El XML no se pudo leer o no tiene la forma de una factura del SRI."""
    pass


def _parse_xml_bytes(raw_xml, error_message):
    try:
        return ElementTree.fromstring(raw_xml)
    except ElementTree.ParseError:
        raise InvalidPurchaseXMLError(error_message)


def _extract_factura_root(raw_xml):
    if not raw_xml or not raw_xml.strip():
        raise InvalidPurchaseXMLError('El archivo XML está vacío.')

    root = _parse_xml_bytes(raw_xml, 'El archivo seleccionado no es un XML válido.')

    if root.tag == 'autorizacion':
        comprobante = root.find('comprobante')
        if comprobante is None or not (comprobante.text or '').strip():
            raise InvalidPurchaseXMLError('El XML de autorización no contiene un comprobante embebido.')
        root = _parse_xml_bytes(
            comprobante.text.strip().encode('utf-8'),
            'El comprobante embebido en el XML de autorización no es válido.'
        )

    if root.tag != 'factura':
        raise InvalidPurchaseXMLError('El XML no corresponde a una factura electrónica del SRI (se esperaba un comprobante tipo "factura").')

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
        raise InvalidPurchaseXMLError(f'El valor de {field_description} en el XML no es un número válido: "{value}"')


def parse_supplier_invoice_xml(raw_xml):
    """
    raw_xml: contenido crudo (bytes) del archivo XML subido.

    Devuelve {'info': {...datos del emisor...}, 'lines': [{'code', 'description', 'cant', 'price'}, ...]}
    o lanza InvalidPurchaseXMLError con un mensaje claro en español.
    """
    if isinstance(raw_xml, str):
        raw_xml = raw_xml.encode('utf-8')

    root = _extract_factura_root(raw_xml)

    info_tributaria = root.find('infoTributaria')
    detalles = root.find('detalles')
    if info_tributaria is None or detalles is None:
        raise InvalidPurchaseXMLError('El XML no tiene la estructura esperada de una factura electrónica del SRI (falta infoTributaria o detalles).')

    detalle_nodes = detalles.findall('detalle')
    if not detalle_nodes:
        raise InvalidPurchaseXMLError('El XML no contiene ningún producto (detalle) para importar.')

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

        lines.append({
            'code': code,
            'description': description,
            'cant': int(cant_decimal.to_integral_value(rounding=ROUND_HALF_UP)),
            'price': price_decimal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        })

    estab = _text(info_tributaria, 'estab')
    pto_emi = _text(info_tributaria, 'ptoEmi')
    secuencial = _text(info_tributaria, 'secuencial')
    # Concatenado en dígitos (sin guiones): el campo "Número de factura" de
    # Compras solo acepta dígitos. Se incluyen establecimiento y punto de
    # emisión (no solo el secuencial) porque el secuencial se reinicia por
    # cada uno; usar solo el secuencial podría chocar entre proveedores.
    invoice_number = f'{estab}{pto_emi}{secuencial}' if estab and pto_emi and secuencial else ''

    info = {
        'ruc': _text(info_tributaria, 'ruc'),
        'razon_social': _text(info_tributaria, 'razonSocial'),
        'clave_acceso': _text(info_tributaria, 'claveAcceso'),
        'estab': estab,
        'pto_emi': pto_emi,
        'secuencial': secuencial,
        'invoice_number': invoice_number,
    }

    return {'info': info, 'lines': lines}

"""Validación de comprobantes electrónicos contra los esquemas XSD oficiales
del SRI (publicados en www.sri.gob.ec > Facturación electrónica), guardados en
core/pos/resources/xsd. Un XML que no cumple el esquema, el SRI lo devuelve; al
validarlo antes de firmar, el error es claro y no se consume el secuencial."""
import os

from lxml import etree

XSD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resources', 'xsd')

_schemas = {}


def validate_xml(xml, xsd_file):
    """Lanza ValueError con el detalle si `xml` (str) no cumple `xsd_file`."""
    schema = _schemas.get(xsd_file)
    if schema is None:
        tree = etree.parse(os.path.join(XSD_DIR, xsd_file))
        # Los esquemas del SRI referencian la firma digital (xmldsig) de un XSD
        # externo que no se distribuye con ellos. Se valida el comprobante ANTES
        # de firmarlo, o sea sin <Signature>: esa referencia se quita solo de la
        # copia en memoria (el archivo oficial no se modifica).
        namespaces = {'xs': 'http://www.w3.org/2001/XMLSchema'}
        for element in tree.xpath('//xs:element[@ref]', namespaces=namespaces):
            if element.get('ref').endswith('Signature'):
                element.getparent().remove(element)
        for node in tree.xpath('//xs:import', namespaces=namespaces):
            node.getparent().remove(node)
        schema = etree.XMLSchema(tree)
        _schemas[xsd_file] = schema
    document = etree.fromstring(xml.encode('utf-8'))
    if not schema.validate(document):
        errors = '; '.join(f'línea {e.line}: {e.message}' for e in list(schema.error_log)[:5])
        raise ValueError(f'El XML no cumple el esquema oficial del SRI ({xsd_file}): {errors}')

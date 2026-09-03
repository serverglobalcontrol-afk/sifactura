CUSTOMER_TYPE = [
    ('retail', 'Público'),
    ('wholesale', 'Distribuidor'),
    ('credit_card', 'Tarjeta de Crédito'),
]

ALL_PAYMENT_TYPES = [
    ('cash', 'Efectivo'),
    ('deposit', 'Deposito'),
    ('transfer', 'Transferencia'),
    ('check', 'Cheque'),
]

PAYMENT_TYPE = (
    ('efectivo', 'Efectivo'),
    ('credito', 'Credito'),
)

VOUCHER_TYPE = (
    ('01', 'FACTURA'),
    ('04', 'NOTA DE CRÉDITO'),
    ('08', 'TICKET DE VENTA'),
    ('COT', 'COTIZACIÓN'),
    # Se agrega al final, nunca en medio: varios lugares del código referencian
    # VOUCHER_TYPE[0][0], [1][0], etc. por posición (no por código), e insertar
    # en medio correría esos índices y rompería esas referencias existentes.
    ('03', 'LIQUIDACIÓN DE COMPRA'),
)

OBLIGATED_ACCOUNTING = (
    ('SI', 'Si'),
    ('NO', 'No'),
)

IDENTIFICATION_TYPE = (
    ('05', 'CEDULA'),
    ('04', 'RUC'),
    ('06', 'PASAPORTE'),
    ('07', 'VENTA A CONSUMIDOR FINAL*'),
    ('08', 'IDENTIFICACION DELEXTERIOR*'),
)

TAX_CODES = (
    (2, 'IVA'),
    (3, 'ICE'),
    (5, 'IRBPNR'),
)

VAT_PERCENTAGE = (
    (0, '0%'),
    (2, '12%'),
    (3, '14%'),
    (4, '15%'),
    (5, '5%'),
    (6, 'No Objeto de Impuesto'),
    (7, 'Exento de IVA'),
    (8, 'IVA diferenciado'),
    (10, '13%'),
)

PAYMENT_METHOD = (
    ('01', 'SIN UTILIZACION DEL SISTEMA FINANCIERO'),
    ('15', 'COMPENSACIÓN DE DEUDAS'),
    ('16', 'TARJETA DE DÉBITO'),
    ('17', 'DINERO ELECTRÓNICO'),
    ('18', 'TARJETA PREPAGO'),
    ('20', 'OTROS CON UTILIZACION DEL SISTEMA FINANCIERO'),
    ('21', 'ENDOSO DE TÍTULOS'),
)

VOUCHER_STAGE = (
    ('xml_creation', 'Creación del XML'),
    ('xml_signature', 'Firma del XML'),
    ('xml_validation', 'Validación del XML'),
    ('xml_authorized', 'Autorización del XML'),
    ('sent_by_email', 'Enviado por email'),
)

INVOICE_STATUS = (
    ('without_authorizing', 'Sin Autorizar'),
    ('authorized', 'Autorizada'),
    ('authorized_and_sent_by_email', 'Autorizada y enviada por email'),
    ('canceled', 'Anulado'),
    ('sequential_registered_error', 'Error de secuencial registrado'),
)

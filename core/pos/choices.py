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

# Tupla propia de Ventas: Purchase sigue usando PAYMENT_TYPE (solo efectivo/
# credito) sin cambios. Se separa para no arrastrar Transferencia/Tarjeta a
# Compras, donde no aplican.
SALE_PAYMENT_TYPE = (
    ('efectivo', 'Efectivo'),
    ('credito', 'Credito'),
    ('transferencia', 'Transferencia'),
    ('tarjeta_credito', 'Tarjeta de Crédito'),
)

CARD_TYPE = (
    ('visa', 'Visa'),
    ('mastercard', 'Mastercard'),
    ('diners', 'Diners Club'),
    ('american_express', 'American Express'),
    ('discover', 'Discover'),
)

CARD_TRANSACTION_TYPE = (
    ('corriente', 'Corriente'),
    ('diferido', 'Diferido'),
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
    # Retención emitida a un proveedor. Al final por la misma razón: el código
    # referencia estos tipos por posición. NO se crea automáticamente por
    # empresa: la serie se crea a mano en Facturación > Comprobantes con el
    # último número real emitido (muchas empresas migran de otro sistema).
    ('07', 'COMPROBANTE DE RETENCIÓN'),
)

RETENTION_KIND = (
    ('renta', 'Impuesto a la renta'),
    ('iva', 'IVA'),
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

CASH_REGISTER_STATUS = (
    ('open', 'Abierta'),
    ('closed', 'Cerrada'),
)

INVOICE_STATUS = (
    ('without_authorizing', 'Sin Autorizar'),
    ('authorized', 'Autorizada'),
    ('authorized_and_sent_by_email', 'Autorizada y enviada por email'),
    ('canceled', 'Anulado'),
    ('sequential_registered_error', 'Error de secuencial registrado'),
)


# Comprobantes que un proveedor puede entregarnos como respaldo de una compra
# (subconjunto de la Tabla 4 del ATS del SRI, "Tipos de comprobantes
# autorizados"). Los códigos son los del SRI; contrastar con el catálogo ATS
# vigente antes de ampliar.
PURCHASE_VOUCHER_TYPE = (
    ('01', 'Factura'),
    ('02', 'Nota o boleta de venta'),
    ('09', 'Tiquete de máquina registradora'),
    ('12', 'Documento emitido por institución financiera'),
    ('15', 'Comprobante de venta emitido en el exterior'),
    ('18', 'Documento autorizado utilizado en ventas (excepto N/C y N/D)'),
    ('19', 'Comprobante de pago de cuotas o aportes'),
    ('20', 'Documento por servicios administrativos de institución del Estado'),
)

# Tabla 5 del ATS: sustento tributario del comprobante.
TAX_SUPPORT = (
    ('01', '01 - Crédito tributario IVA (servicios y bienes que no son inventario ni activo fijo)'),
    ('02', '02 - Costo o gasto para IR (servicios y bienes que no son inventario ni activo fijo)'),
    ('03', '03 - Activo fijo: crédito tributario IVA'),
    ('04', '04 - Activo fijo: costo o gasto para IR'),
    ('05', '05 - Liquidación de gastos de viaje, hospedaje y alimentación (IR)'),
    ('06', '06 - Inventario: crédito tributario IVA'),
    ('07', '07 - Inventario: costo o gasto para IR'),
    ('08', '08 - Valor pagado para solicitar reembolso de gasto (intermediario)'),
    ('09', '09 - Reembolso por siniestros'),
    ('10', '10 - Distribución de dividendos, beneficios o utilidades'),
    ('11', '11 - Convenios de débito o recaudación para IFI'),
    ('12', '12 - Impuestos y retenciones presuntivos'),
    ('13', '13 - Valores reconocidos por entidades del sector público'),
    ('00', '00 - Caso especial cuyo sustento no aplica en las opciones anteriores'),
)

# Tipo de IVA de cada línea de una compra. Cada uno cae en una base distinta
# del ATS: iva -> baseImpGrav, 0 -> baseImponible, no_objeto -> baseNoGraIva,
# exento -> baseImpExe.
PURCHASE_TAX_TYPE = (
    ('iva', 'IVA'),
    ('0', 'IVA 0%'),
    ('no_objeto', 'No objeto de IVA'),
    ('exento', 'Exento de IVA'),
)

# Tarifas de IVA (%) que se aceptan en una línea gravada (las vigentes y
# anteriores que un proveedor todavía puede haber facturado).
VALID_IVA_PERCENTS = (5, 8, 12, 13, 14, 15)

SUPPLIER_ID_TYPE = (
    ('01', 'RUC'),
    ('02', 'Cédula'),
    ('03', 'Pasaporte / identificación del exterior'),
)

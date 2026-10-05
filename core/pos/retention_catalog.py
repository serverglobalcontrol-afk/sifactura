"""Catálogo de conceptos de retención (renta e IVA) sembrado desde fuentes OFICIALES del SRI.

- Renta: Catálogo ATS (hoja "TABLAS RETENCIONES", columna vigente "Desde 06/08/2026", pagos a
  residentes), publicado en www.sri.gob.ec > Anexos y guías (actualización 06-08-2026).
- IVA: Tabla 20 de la Ficha Técnica de Comprobantes Electrónicos Offline v2.34 (julio 2026).

Los porcentajes de renta cambian por resolución del SRI: este archivo es solo la SIEMBRA inicial;
cada empresa los ajusta en Facturación > Conceptos de retención y la siembra nunca pisa lo ya editado.
Los conceptos cuyo porcentaje depende del caso ("varios porcentajes", "12 o 14"...) quedan sin
porcentaje: se ingresa a mano al emitir.
"""

SOURCE = 'Catálogo ATS del SRI (06-08-2026) y Ficha Técnica offline v2.34'

# (código, concepto, porcentaje o None si varía, nota del catálogo)
RENTA_CONCEPTS = [
    ('303', 'Honorarios profesionales y demás pagos por servicios relacionados con el título profesional', 10.0, ''),
    ('303A', 'Servicios profesionales prestados por sociedades residentes', 5.0, ''),
    ('304', 'Servicios predomina el intelecto no relacionados con el título profesional', 10.0, ''),
    ('304A', 'Comisiones y demás pagos por servicios predomina intelecto no relacionados con el título profesional', 10.0, ''),
    ('304B', 'Pagos a notarios y registradores de la propiedad y mercantil por sus actividades ejercidas como tales', 10.0, ''),
    ('304C', 'Pagos a deportistas, entrenadores, árbitros, miembros del cuerpo técnico por sus actividades ejercidas como tales', 10.0, ''),
    ('304D', 'Pagos a artistas por sus actividades ejercidas como tales', 10.0, ''),
    ('304E', 'Honorarios y demás pagos por servicios de docencia', 10.0, ''),
    ('307', 'Servicios predomina la mano de obra', 3.0, ''),
    ('308', 'Utilización o aprovechamiento de la imagen o renombre (personas naturales, sociedades," influencers")', 10.0, ''),
    ('309', 'Servicios prestados por medios de comunicación y agencias de publicidad', 3.0, ''),
    ('310', 'Servicio de transporte privado de pasajeros o transporte público o privado de carga', None, '1 /0 según resolución NAC-DGERCGC26-00000028'),
    ('311', 'Pagos a través de liquidación de compra (nivel cultural o rusticidad)', 3.0, ''),
    ('312', 'Transferencia de bienes muebles de naturaleza corporal', 2.0, ''),
    ('312A', 'COMPRAS AL PRODUCTOR: de bienes de origen bioacuático, forestal y los descritos el art.27.1 de LRTI', 1.0, ''),
    ('312C', 'COMPRAS AL COMERCIALIZADOR: de bienes de origen bioacuático, forestal y los descritos el art.27.1 de LRTI', 1.75, ''),
    ('314A', 'Regalías por concepto de franquicias de acuerdo al Código INGENIOS (COESCCI) - pago a personas naturales', 10.0, ''),
    ('314B', 'Cánones, derechos de autor, marcas, patentes y similares de acuerdo al Código INGENIOS (COESCCI) – pago a personas naturales', 10.0, ''),
    ('314C', 'Regalías por concepto de franquicias de acuerdo al Código INGENIOS (COESCCI) - pago a sociades', 10.0, ''),
    ('314D', 'Cánones, derechos de autor, marcas, patentes y similares de acuerdo al Código INGENIOS (COESCCI)', 10.0, ''),
    ('319', 'Cuotas de arrendamiento mercantil (prestado por sociedades), inclusive la de opción de compra', 2.0, ''),
    ('320', 'Arrendamiento bienes inmuebles', 10.0, ''),
    ('322', 'Seguros y reaseguros (primas y cesiones)', 2.0, ''),
    ('323', 'Rendimientos financieros pagados a naturales y sociedades (No a IFIs)', 3.0, ''),
    ('323A', 'Rendimientos financieros depósitos Cta. Corriente', 3.0, ''),
    ('323B1', 'Rendimientos financieros depósitos Cta. Ahorros Sociedades', 3.0, ''),
    ('323E', 'Rendimientos financieros depósito a plazo fijo gravados', 3.0, ''),
    ('323E2', 'Rendimientos financieros depósito a plazo fijo exentos', 0.0, ''),
    ('323F', 'Rendimientos financieros operaciones de reporto - repos', 3.0, ''),
    ('323G', 'Inversiones (captaciones) rendimientos distintos de aquellos pagados a IFIs', 3.0, ''),
    ('323H', 'Rendimientos financieros obligaciones', 3.0, ''),
    ('323I', 'Rendimientos financieros bonos convertible en acciones', 3.0, ''),
    ('323 M', 'Rendimientos financieros : Inversiones en títulos valores en renta fija gravados', 3.0, ''),
    ('323 N', 'Rendimientos financieros Inversiones en títulos valores en renta fija exentos', 0.0, ''),
    ('323 O', 'Intereses y demás rendimientos financieros pagados a bancos y otras entidades sometidas al control de la Superintendencia de Bancos y de la Economía Popular y Solidaria', 0.0, ''),
    ('323 P', 'Intereses pagados por entidades del sector público a favor de sujetos pasivos', 3.0, ''),
    ('323Q', 'Otros intereses y rendimientos financieros gravados', 3.0, ''),
    ('323R', 'Otros intereses y rendimientos financieros exentos', 0.0, ''),
    ('323S', 'Pagos y créditos en cuenta efectuados por el BCE y los depósitos centralizados de valores, en calidad de intermediarios, a instituciones del sistema financiero por cuenta de otras personas naturales y sociedades', 3.0, ''),
    ('323T', 'Rendimientos financieros originados en la deuda pública ecuatoriana', 0.0, ''),
    ('323U', 'Rendimientos financieros originados en títulos valores de obligaciones de 360 días o más para el financiamiento de proyectos públicos en asociación público-privada', 0.0, ''),
    ('324A', 'Intereses en operaciones de crédito entre instituciones del sistema financiero y entidades economía popular y solidaria.', 2.0, ''),
    ('324B', 'Inversiones entre instituciones del sistema financiero y entidades economía popular y solidaria', 2.0, ''),
    ('324C', 'Pagos y créditos en cuenta efectuados por el BCE y los depósitos centralizados de valores, en calidad de intermediarios, a instituciones del sistema financiero por cuenta de otras instituciones del sistema financiero', 2.0, ''),
    ('325', 'Anticipo dividendos', 25.0, ''),
    ('325A', 'Préstamos accionistas, beneficiarios o partícipes residentes o establecidos en el Ecuador', 25.0, ''),
    ('3250', 'Dividendos exentos (por no llegar a franja exenta o beneficio de otras leyes)', 0.0, ''),
    ('326', 'Dividendos distribuidos que correspondan al impuesto a la renta único establecido en el art. 27 de la LRTI', None, '12 o 14'),
    ('327', 'Dividendos distribuidos a personas naturales residentes', None, '12 o 14'),
    ('328', 'Dividendos distribuidos a sociedades residentes', 0.0, ''),
    ('329', 'Dividendos distribuidos a fideicomisos residentes', 0.0, ''),
    ('331', 'Dividendos en acciones (capitalización de utilidades)', 0.0, ''),
    ('332', 'Otras compras de bienes y servicios no sujetas a retención (incluye régimen RIMPE - Negocios Populares, para este caso aplica con cualquier forma de pago inclusive los pagos que deban realizar las tarjetas de crédito/débito)', 0.0, ''),
    ('332B', 'Compra de bienes inmuebles', 0.0, ''),
    ('332C', 'Transporte público de pasajeros', 0.0, ''),
    ('332D', 'Pagos en el país por transporte de pasajeros o transporte internacional de carga, a compañías nacionales o extranjeras de aviación o marítimas', 0.0, ''),
    ('332E', 'Valores entregados por las cooperativas de transporte a sus socios', None, '0 /1 según resolución NAC-DGERCGC26-00000028'),
    ('332F', 'Compraventa de divisas distintas al dólar de los Estados Unidos de América', 0.0, ''),
    ('332G', 'Pagos con tarjeta de crédito', 0.0, ''),
    ('332H', 'Pago al exterior tarjeta de crédito reportada por la Emisora de tarjeta de crédito, solo recap', 0.0, ''),
    ('332I', 'Pago a través de convenio de debito (Clientes IFI`s)', 0.0, ''),
    ('333', 'Ganancia en la enajenación de derechos representativos de capital u otros derechos que permitan la exploración, explotación, concesión o similares de sociedades, que se coticen en bolsa de valores del Ecuador', 10.0, ''),
    ('334', 'Contraprestación producida por la enajenación de derechos representativos de capital u otros derechos que permitan la exploración, explotación, concesión o similares de sociedades, no cotizados en bolsa de valores del Ecuador', 2.0, ''),
    ('335', 'Loterías, rifas, pronósticos deportivos, apuestas y similares', 15.0, ''),
    ('336', 'Venta de combustibles a comercializadoras', None, '2/mil'),
    ('337', 'Venta de combustibles a distribuidores', None, '3/mil'),
    ('338', 'Producción y venta local de banano producido o no por el mismo sujeto pasivo', None, '1 a 2'),
    ('340', 'Impuesto único a la exportación de banano', 3.0, ''),
    ('343', 'Otras retenciones aplicables el 1% (incluye régimen RIMPE - Emprendedores, para este caso aplica con cualquier forma de pago inclusive los pagos que deban realizar las tarjetas de crédito/débito)', 1.0, ''),
    ('343A', 'Energía eléctrica', 2.0, ''),
    ('343B', 'Actividades de construcción de obra material inmueble, urbanización, lotización o actividades similares', 2.0, ''),
    ('343C', 'Recepción de botellas plásticas no retornables de PET', 2.0, ''),
    ('3440', 'Otras retenciones aplicables el 3% (incluye pago utilidades a extrabajadores)', 3.0, ''),
    ('344A', 'Pago local tarjeta de crédito /débito reportada por la Emisora de tarjeta de crédito / entidades del sistema financiero/sistemas auxiliares de pago', 2.0, ''),
    ('344B', 'Adquisición de sustancias minerales dentro del territorio nacional', 2.0, ''),
    ('346', 'Otras retenciones aplicables a otros porcentajes', None, 'varios porcentajes'),
    ('346A', 'Otras ganancias de capital distintas de enajenación de derechos representativos de capital', None, 'varios porcentajes'),
    ('346B', 'Donaciones en dinero -Impuesto a las donaciones', None, 'Conforme Art 36 LRTI literal d)'),
    ('346C', 'Retención a cargo del propio sujeto pasivo por la producción y/o comercialización de minerales y otros bienes', None, '0 a 10 (NAC-DGERCGC16-00000217 y sus reformas)'),
    ('346D', 'Retención a cargo del propio sujeto pasivo por la comercialización de productos forestales', None, '0 o 10'),
    ('350', 'Otras autorretenciones (inciso 1 y 2 Art.92.1 RLRTI)', None, '1,50 o 1,75'),
    ('3480', 'Impuesto a la renta único sobre los ingresos percibidos por los operadores de pronósticos deportivos', 15.0, ''),
    ('3481', 'Autorretenciones Sociedades Grandes Contribuyentes', None, 'varios porcentajes (Conforme RESOLUCIÓN No. NAC-DGERCGC24-00000024 y sus reformas)'),
    ('3482', 'Comisiones a sociedades, nacionales o extranjeras residentes y establecimientos permanentes domiciliados en el país', 5.0, ''),
]

# Tabla 20 de la ficha técnica: retención de IVA (porcentaje -> código SRI).
IVA_CONCEPTS = [
    ('9', 'Retención de IVA 10%', 10.0, ''),
    ('10', 'Retención de IVA 20%', 20.0, ''),
    ('1', 'Retención de IVA 30%', 30.0, ''),
    ('11', 'Retención de IVA 50%', 50.0, ''),
    ('2', 'Retención de IVA 70%', 70.0, ''),
    ('3', 'Retención de IVA 100%', 100.0, ''),
    ('7', 'Retención de IVA en cero (0%)', 0.0, 'Disposición Transitoria Única de la Resolución NAC-DGERCGC15-00000284'),
]


def seed_retention_concepts(model):
    """Crea los conceptos que falten. Idempotente: NO modifica los que ya existen
    (la empresa pudo ajustar su porcentaje o desactivarlos)."""
    created = 0
    for kind, concepts in (('renta', RENTA_CONCEPTS), ('iva', IVA_CONCEPTS)):
        for code, description, percentage, note in concepts:
            _, was_created = model.objects.get_or_create(
                kind=kind, code=code,
                defaults={'description': description, 'percentage': percentage, 'note': note},
            )
            created += int(was_created)
    return created

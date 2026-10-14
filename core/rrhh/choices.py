MONTHS = (
    ('', '-----------'),
    (1, 'Enero'),
    (2, 'Febrero'),
    (3, 'Marzo'),
    (4, 'Abril'),
    (5, 'Mayo'),
    (6, 'Junio'),
    (7, 'Julio'),
    (8, 'Agosto'),
    (9, 'Septiembre'),
    (10, 'Octubre'),
    (11, 'Noviembre'),
    (12, 'Diciembre')
)

TYPE_HEADINGS = (
    ('haberes', 'HABERES'),
    ('descuentos', 'DESCUENTOS'),
)


# ---- RDEP (Anexo de retenciones en la fuente bajo relación de dependencia) ----
# Códigos de las tablas de la Ficha Técnica del SRI (ejercicio 2024, vigente para 2025/2026).
RDEP_ID_TYPE = (
    ('C', 'Cédula'),
    ('E', 'Identificación tributaria del exterior'),
    ('P', 'Pasaporte'),
)

RDEP_RESIDENCE = (
    ('01', 'Residente local'),
    ('02', 'Residente del exterior'),
)

RDEP_TREATY = (
    ('NA', 'No aplica'),
    ('NO', 'Sin convenio'),
    ('SI', 'Con convenio'),
)

RDEP_DISABILITY = (
    ('01', 'No aplica'),
    ('02', 'Trabajador con discapacidad'),
    ('03', 'Trabajador sustituto de una persona con discapacidad'),
    ('04', 'Trabajador con cónyuge, pareja o hijo con discapacidad a su cargo (hasta el período 2023)'),
)

RDEP_YES_NO = (
    ('NO', 'No'),
    ('SI', 'Sí'),
)

RDEP_DEPENDENTS = (
    (0, '0 cargas familiares'),
    (1, '1 carga familiar'),
    (2, '2 cargas familiares'),
    (3, '3 cargas familiares'),
    (4, '4 cargas familiares'),
    (5, '5 o más cargas familiares'),
)

RDEP_NET_SALARY = (
    ('1', 'Sin sistema de salario neto'),
    ('2', 'Con sistema de salario neto'),
)

RDEP_EMPLOYER_TYPE = (
    ('PRIVADO_MIXTO', 'Privado o mixto'),
    ('PUBLICO', 'Público o IFIS'),
)

RDEP_SOCIAL_SECURITY = (
    ('IESS', 'IESS'),
    ('ISSFA_ISSPOL', 'ISSFA o ISSPOL'),
)

# Casilla del RDEP a la que corresponde cada rubro de nómina (Headings.rdep_field).
# El nombre es el del campo del XML del SRI.
RDEP_FIELDS = (
    ('suelSal', 'Sueldos, salarios y otros ingresos gravados (materia gravada del IESS)'),
    ('sobSuelComRemu', 'Otros ingresos gravados (sobresueldos, comisiones; no materia del IESS)'),
    ('partUtil', 'Participación de utilidades'),
    ('decimTer', 'Décimo tercer sueldo'),
    ('decimCuar', 'Décimo cuarto sueldo'),
    ('fondoReserva', 'Fondo de reserva'),
    ('salarioDigno', 'Compensación económica por salario digno'),
    ('otrosIngRenGrav', 'Otros ingresos en relación de dependencia que no son materia gravada'),
    ('apoPerIess', 'Aporte personal al IESS (descuento al trabajador)'),
    ('valRet', 'Impuesto a la renta retenido al trabajador'),
)

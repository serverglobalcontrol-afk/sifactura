"""Plan de cuentas base que se precarga al activar la contabilidad de una
empresa.

Es un plan genérico de comercio al por menor, de 4 niveles, inspirado en el
esquema NIIF para PYMES (1 Activo, 2 Pasivo, 3 Patrimonio, 4 Ingresos,
5 Costos, 6 Gastos). NO pretende ser el catálogo oficial de la
Superintendencia de Compañías: cada empresa puede editarlo, y su contador
debe revisarlo antes de usarlo para declarar.
"""

# (código, nombre, tipo, acepta movimientos)
CHART = [
    ('1', 'ACTIVO', 'activo', False),
    ('1.1', 'ACTIVO CORRIENTE', 'activo', False),
    ('1.1.01', 'EFECTIVO Y EQUIVALENTES DE EFECTIVO', 'activo', False),
    ('1.1.01.01', 'Caja general', 'activo', True),
    ('1.1.01.02', 'BANCOS', 'activo', False),
    ('1.1.01.02.01', 'Banco por defecto', 'activo', True),
    ('1.1.01.03', 'Tarjetas de crédito por cobrar', 'activo', True),
    ('1.1.02', 'CUENTAS POR COBRAR', 'activo', False),
    ('1.1.02.01', 'Clientes', 'activo', True),
    ('1.1.03', 'CRÉDITO TRIBUTARIO', 'activo', False),
    ('1.1.03.01', 'Crédito tributario IVA en compras', 'activo', True),
    ('1.1.03.02', 'IVA retenido por clientes', 'activo', True),
    ('1.1.03.03', 'Impuesto a la renta retenido por clientes', 'activo', True),
    ('1.1.04', 'INVENTARIOS', 'activo', False),
    ('1.1.04.01', 'Inventario de mercaderías', 'activo', True),
    ('2', 'PASIVO', 'pasivo', False),
    ('2.1', 'PASIVO CORRIENTE', 'pasivo', False),
    ('2.1.01', 'CUENTAS POR PAGAR', 'pasivo', False),
    ('2.1.01.01', 'Proveedores', 'pasivo', True),
    ('2.1.02', 'OBLIGACIONES TRIBUTARIAS', 'pasivo', False),
    ('2.1.02.01', 'IVA cobrado en ventas', 'pasivo', True),
    ('2.1.02.02', 'Retención de IVA por pagar', 'pasivo', True),
    ('2.1.02.03', 'Retención en la fuente de renta por pagar', 'pasivo', True),
    ('2.1.03', 'OBLIGACIONES CON EL PERSONAL', 'pasivo', False),
    ('2.1.03.01', 'Sueldos por pagar', 'pasivo', True),
    ('2.1.03.02', 'Descuentos de nómina por pagar', 'pasivo', True),
    ('3', 'PATRIMONIO', 'patrimonio', False),
    ('3.1', 'CAPITAL', 'patrimonio', False),
    ('3.1.01', 'Capital social o capital propio', 'patrimonio', True),
    ('3.1.02', 'Aportes de socios o propietario', 'patrimonio', True),
    ('3.2', 'RESULTADOS', 'patrimonio', False),
    ('3.2.01', 'Resultados acumulados', 'patrimonio', True),
    ('3.2.02', 'Resultado del ejercicio', 'patrimonio', True),
    ('4', 'INGRESOS', 'ingreso', False),
    ('4.1', 'INGRESOS DE ACTIVIDADES ORDINARIAS', 'ingreso', False),
    ('4.1.01', 'Ventas con IVA', 'ingreso', True),
    ('4.1.02', 'Ventas tarifa 0%', 'ingreso', True),
    ('4.1.03', 'Devoluciones en ventas', 'ingreso', True),
    ('4.2', 'OTROS INGRESOS', 'ingreso', False),
    ('4.2.01', 'Otros ingresos', 'ingreso', True),
    ('4.2.02', 'Sobrante de caja', 'ingreso', True),
    ('5', 'COSTOS', 'costo', False),
    ('5.1', 'COSTO DE VENTAS', 'costo', False),
    ('5.1.01', 'Costo de ventas', 'costo', True),
    ('5.1.02', 'Compras no inventariables', 'costo', True),
    ('6', 'GASTOS', 'gasto', False),
    ('6.1', 'GASTOS OPERACIONALES', 'gasto', False),
    ('6.1.01', 'Sueldos y salarios', 'gasto', True),
    ('6.1.02', 'Gastos generales', 'gasto', True),
    ('6.1.03', 'Gastos bancarios', 'gasto', True),
    ('6.1.04', 'Faltante de caja', 'gasto', True),
    ('6.1.05', 'Ajuste por redondeo', 'gasto', True),
]

# rol -> código de cuenta por defecto
DEFAULT_ROLE_ACCOUNTS = {
    'caja': '1.1.01.01',
    'banco_defecto': '1.1.01.02.01',
    'tarjetas': '1.1.01.03',
    'clientes': '1.1.02.01',
    'proveedores': '2.1.01.01',
    'inventario': '1.1.04.01',
    'iva_compras': '1.1.03.01',
    'ret_iva': '1.1.03.02',
    'ret_renta': '1.1.03.03',
    'iva_ventas': '2.1.02.01',
    'ret_iva_pagar': '2.1.02.02',
    'ret_renta_pagar': '2.1.02.03',
    'sueldos_pagar': '2.1.03.01',
    'descuentos_nomina': '2.1.03.02',
    'ventas_gravadas': '4.1.01',
    'ventas_0': '4.1.02',
    'devoluciones': '4.1.03',
    'ingreso_defecto': '4.2.01',
    'sobrante_caja': '4.2.02',
    'costo_ventas': '5.1.01',
    'compras_no_inv': '5.1.02',
    'sueldos_gasto': '6.1.01',
    'gasto_defecto': '6.1.02',
    'gasto_bancario': '6.1.03',
    'faltante_caja': '6.1.04',
    'redondeo': '6.1.05',
}

# Código de la cuenta padre bajo la que se crea la cuenta contable de cada
# cuenta bancaria nueva.
BANKS_PARENT_CODE = '1.1.01.02'

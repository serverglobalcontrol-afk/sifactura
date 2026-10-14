"""RDEP: Anexo de retenciones en la fuente de Impuesto a la Renta bajo relación de dependencia.

Este módulo reúne lo que NO depende de la base de datos para poder probarlo solo:
el cálculo del impuesto causado con la tabla anual (art. 36 LRTI) y la rebaja por
gastos personales (Ficha Técnica del SRI, sección 1.5). Los valores de cada año
(tabla, canasta familiar básica) se guardan en RdepYear / RdepTaxBracket y los
confirma el contador: aquí solo se SUGIEREN los del SRI para 2026.
"""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')
ZERO = Decimal('0.00')

# Canastas familiares básicas (múltiplos de la CFB) que limitan la rebaja, según el número de cargas.
BASKETS_BY_DEPENDENTS = {0: 7, 1: 9, 2: 11, 3: 14, 4: 17, 5: 20}
BASKETS_CATASTROPHIC = 100
REBATE_RATE = Decimal('0.18')

# Valores publicados por el SRI para el ejercicio 2026 (resolución NAC-DGERCGC25-00000043; canasta de
# enero 2026 según boletín del SRI). Son una SUGERENCIA para precargar: el contador debe confirmarlos.
SUGGESTED_YEARS = {
    2026: {
        'basic_basket': '821.80',
        'source': 'SRI: resolución NAC-DGERCGC25-00000043 (tabla 2026) y canasta familiar básica de enero 2026. Confirmar con el contador.',
        # (fracción básica, exceso hasta, impuesto fracción básica, % fracción excedente)
        'brackets': [
            ('0', '12208', '0', '0'), ('12208', '15549', '0', '5'), ('15549', '20188', '167', '10'), ('20188', '26700', '631', '12'),
            ('26700', '35136', '1412', '15'), ('35136', '46575', '2678', '20'), ('46575', '62005', '4965', '25'),
            ('62005', '82679', '8823', '30'), ('82679', '109956', '15025', '35'), ('109956', None, '24572', '37'),
        ],
    },
}


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def income_tax(base, brackets):
    """Impuesto causado = impuesto de la fracción básica + (base - fracción básica) x %.
    `brackets`: lista de dicts/objetos con lower, upper (None = sin límite), base_tax, rate."""
    base = money(base)
    if base <= 0:
        return ZERO
    chosen = None
    for bracket in sorted(brackets, key=lambda b: Decimal(str(_get(b, 'lower')))):
        if base > Decimal(str(_get(bracket, 'lower'))):
            chosen = bracket  # la última fracción cuyo inicio queda por debajo de la base
    if chosen is None:
        raise ValueError('La base imponible no entra en ninguna fracción de la tabla de impuesto: revisa los Parámetros del RDEP.')
    lower = Decimal(str(_get(chosen, 'lower')))
    return money(Decimal(str(_get(chosen, 'base_tax'))) + (base - lower) * Decimal(str(_get(chosen, 'rate'))) / Decimal('100'))


def personal_expenses_rebate(total_expenses, dependents, catastrophic, basic_basket, galapagos=False, galapagos_index=Decimal('1')):
    """Rebaja por gastos personales = 18% del MENOR entre el total de gastos y el tope
    (canasta familiar básica x canastas según cargas; 100 si es o tiene a cargo una
    persona con discapacidad o enfermedad catastrófica). En Galápagos el tope se
    multiplica por el IPCEG."""
    baskets = BASKETS_CATASTROPHIC if catastrophic else BASKETS_BY_DEPENDENTS[min(max(int(dependents), 0), 5)]
    cap = Decimal(str(basic_basket)) * baskets
    if galapagos:
        cap *= Decimal(str(galapagos_index))
    return money(min(money(total_expenses), cap) * REBATE_RATE)


def _get(item, name):
    return item[name] if isinstance(item, dict) else getattr(item, name)

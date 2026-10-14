from django.test import SimpleTestCase

from django.test import TestCase

# Create your tests here.


class RdepTaxCalculationTests(SimpleTestCase):
    """Cálculo del impuesto causado y de la rebaja por gastos personales (sin base de datos)."""

    def _brackets(self):
        from core.rrhh.services import rdep
        return [{'lower': a, 'upper': b, 'base_tax': c, 'rate': d} for a, b, c, d in rdep.SUGGESTED_YEARS[2026]['brackets']]

    def test_income_below_the_first_fraction_pays_nothing(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        self.assertEqual(rdep.income_tax(D('10000'), self._brackets()), D('0.00'))
        self.assertEqual(rdep.income_tax(D('0'), self._brackets()), D('0.00'))

    def test_income_inside_a_fraction_adds_the_excess_at_its_rate(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        # 15549-20188: 167 + (20000 - 15549) x 10% = 612.10
        self.assertEqual(rdep.income_tax(D('20000'), self._brackets()), D('612.10'))
        # 12208-15549: (13000 - 12208) x 5% = 39.60
        self.assertEqual(rdep.income_tax(D('13000'), self._brackets()), D('39.60'))

    def test_the_last_fraction_has_no_upper_limit(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        # 109956 en adelante: 24572 + (150000 - 109956) x 37%
        self.assertEqual(rdep.income_tax(D('150000'), self._brackets()), D('39388.28'))

    def test_a_table_that_does_not_cover_the_base_asks_to_review_the_parameters(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        with self.assertRaises(ValueError):
            rdep.income_tax(D('100'), [{'lower': 500, 'upper': None, 'base_tax': 0, 'rate': 5}])

    def test_rebate_is_18_percent_of_the_smaller_of_expenses_and_the_cap(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        # Ejemplo oficial del SRI (RDEP 2023): sin cargas, gastos de 18000, canasta 764.71 -> tope 7 canastas -> 963.53
        self.assertEqual(rdep.personal_expenses_rebate(D('18000'), 0, False, D('764.71')), D('963.53'))
        # Gastos menores que el tope: 18% de los gastos
        self.assertEqual(rdep.personal_expenses_rebate(D('1000'), 0, False, D('821.80')), D('180.00'))

    def test_dependents_and_catastrophic_illness_raise_the_cap(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        big = D('50000')
        self.assertEqual(rdep.personal_expenses_rebate(big, 2, False, D('821.80')), D('1627.16'))   # 11 canastas
        self.assertEqual(rdep.personal_expenses_rebate(big, 9, False, D('821.80')), D('2958.48'))   # 5 o más: 20 canastas
        self.assertEqual(rdep.personal_expenses_rebate(D('100000'), 0, True, D('821.80')), D('14792.40'))   # 100 canastas

    def test_galapagos_multiplies_the_cap_by_the_price_index(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        value = rdep.personal_expenses_rebate(D('50000'), 0, False, D('800'), galapagos=True, galapagos_index=D('1.5'))
        self.assertEqual(value, D('1512.00'))   # 800 x 7 x 1.5 x 18%

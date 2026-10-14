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


class RdepEmployeeCalculationTests(SimpleTestCase):
    """Cálculo por empleado y XML del RDEP, contrastados con el ejemplo oficial del SRI (2023)."""

    def _person(self, **over):
        person = {
            'id_type': 'C', 'id_number': '1700000003', 'last_names': 'PRUEBA', 'first_names': 'PRUEBA', 'establishment': '002',
            'residence': '01', 'country': '593', 'treaty': 'NA', 'disability': '02', 'disability_percent': 80,
            'disability_id_type': 'N', 'disability_id': '999', 'dependents': 0, 'galapagos': 'NO', 'catastrophic': 'NO', 'net_salary': '1',
        }
        person.update(over)
        return person

    def _example_row(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        amounts = {'suelSal': D('20000'), 'sobSuelComRemu': D('10000'), 'partUtil': D('10000'), 'decimTer': D('2000'), 'decimCuar': D('475'), 'apoPerIess': D('1890'), 'valRet': D('649.99')}
        manual = {'other_employers_income': D('10000'), 'other_employers_iess': D('2000'), 'expenses_health': D('18000'), 'exoneration_disability': D('18755.20')}
        # El impuesto causado del ejemplo (1613.52) sale de la tabla 2023; aquí se fija con una fracción de prueba.
        brackets = [{'lower': 0, 'upper': None, 'base_tax': '1613.52', 'rate': 0}]
        return rdep.compute_employee(self._person(), amounts, manual, brackets, D('764.71'))

    def test_the_official_example_employee_gives_the_official_figures(self):
        from decimal import Decimal as D
        row = self._example_row()
        self.assertEqual(row['ingGravConEsteEmpl'], D('40000.00'))
        self.assertEqual(row['basImp'], D('27354.80'))
        self.assertEqual(row['rebajaGastosPersonales'], D('963.53'))
        self.assertEqual(row['impuestoRentaRebajaGastosPersonales'], D('649.99'))
        self.assertEqual(row['expected_retention'], D('649.99'))

    def test_a_second_official_example_with_elderly_exoneration(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        amounts = {'suelSal': D('20000'), 'apoPerIess': D('1500')}
        manual = {'other_employers_income': D('10000'), 'other_employers_iess': D('2000'), 'exoneration_elderly': D('11722')}
        row = rdep.compute_employee(self._person(disability='01', disability_percent=0), amounts, manual, [{'lower': 0, 'upper': None, 'base_tax': 0, 'rate': 0}], D('764.71'))
        self.assertEqual(row['ingGravConEsteEmpl'], D('20000.00'))
        self.assertEqual(row['basImp'], D('14778.00'))

    def test_the_rebate_never_exceeds_the_tax_caused(self):
        from decimal import Decimal as D
        from core.rrhh.services import rdep
        row = rdep.compute_employee(self._person(disability='01', disability_percent=0), {'suelSal': D('15000')}, {'expenses_health': D('9000')},
                                    [{'lower': 0, 'upper': None, 'base_tax': '100', 'rate': 0}], D('821.80'))
        self.assertEqual(row['rebajaGastosPersonales'], D('100.00'))
        self.assertEqual(row['impuestoRentaRebajaGastosPersonales'], D('0.00'))

    def test_the_xml_complies_with_the_official_schema(self):
        from core.rrhh.services import rdep
        header = {'ruc': '0603164773001', 'year': 2023, 'employer_type': 'PRIVADO_MIXTO', 'social_security': 'IESS'}
        data = rdep.render_xml(header, [{'person': self._person(), 'row': self._example_row()}])
        self.assertEqual(rdep.validate_xml(data), [])
        self.assertIn(b'<valRet>649.99</valRet>', data)
        self.assertTrue(data.startswith(b'<?xml version="1.0" encoding="ISO-8859-1" standalone="yes"?>'))

    def test_a_zero_rdep_without_employees_is_valid(self):
        from core.rrhh.services import rdep
        data = rdep.render_xml({'ruc': '0603164773001', 'year': 2026, 'employer_type': 'PRIVADO_MIXTO', 'social_security': 'IESS'}, [])
        self.assertEqual(rdep.validate_xml(data), [])

    def test_the_schema_rejects_an_invalid_identity(self):
        from core.rrhh.services import rdep
        header = {'ruc': '0603164773001', 'year': 2023, 'employer_type': 'PRIVADO_MIXTO', 'social_security': 'IESS'}
        data = rdep.render_xml(header, [{'person': self._person(last_names='X'), 'row': self._example_row()}])
        self.assertTrue(rdep.validate_xml(data))

    def test_names_are_cleaned_and_split(self):
        from core.rrhh.services import rdep
        self.assertEqual(rdep.clean_person_name('Peña Núñez, José'), 'PENA NUNEZ JOSE')
        self.assertEqual(rdep.split_full_name('Calderon Moreta Edgar Fernando'), ('CALDERON MORETA', 'EDGAR FERNANDO'))
        self.assertEqual(rdep.split_full_name('Maria Perez'), ('MARIA', 'PEREZ'))

    def test_zip_holds_the_xml(self):
        import io
        import zipfile
        from core.rrhh.services import rdep
        content = rdep.build_zip(2026, b'<rdep/>')
        self.assertEqual(zipfile.ZipFile(io.BytesIO(content)).namelist(), ['RDEP2026.xml'])

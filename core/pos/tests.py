"""
Pruebas automáticas para las partes más delicadas del sistema:

- El dígito verificador (módulo 11) que hace válida la clave de acceso de
  cada comprobante electrónico ante el SRI.
- Que una respuesta inesperada del SRI (por ejemplo, bloqueada por su
  firewall) no tumbe el sistema, sino que devuelva un error legible.
- El cálculo de subtotal, descuento e IVA de una cotización.
- Que la numeración secuencial de comprobantes nunca se repita ni salte.

No se hace ninguna llamada real a internet: las pruebas del SRI usan una
clave de acceso real que el ambiente de certificación del SRI ya autorizó
en esta misma sesión (Sale #8, empresa_prueba, 2026-08-31), y simulan
(mock) las respuestas de red en vez de contactar el servicio de verdad.
"""
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase
from django_tenants.test.cases import FastTenantTestCase

from core.pos.models import Category, Client, Product, Quotation, QuotationDetail, Receipt, VOUCHER_TYPE
from core.pos.utilities.sri import SRI
from core.tenant.models import Company, Plan
from core.user.models import User


class SRIAccessKeyTests(SimpleTestCase):
    """compute_mod11 es el algoritmo de dígito verificador que el SRI exige
    en la clave de acceso de cada factura electrónica. Si este cálculo
    falla, TODAS las facturas que emita el sistema quedarían inválidas."""

    def test_compute_mod11_matches_a_real_sri_authorized_access_key(self):
        # Clave de acceso real de la Venta #8 (empresa_prueba), autorizada
        # de verdad por el ambiente de certificación del SRI el 2026-08-31.
        real_access_key = '3108202601100237602600110060010045164692018179110'
        key_without_check_digit = real_access_key[:-1]
        expected_check_digit = real_access_key[-1]

        self.assertEqual(
            SRI().compute_mod11(pass_key_48=key_without_check_digit),
            expected_check_digit,
        )

    def test_compute_mod11_rejects_keys_longer_than_48_chars(self):
        self.assertEqual(SRI().compute_mod11(pass_key_48='1' * 49), '')


class SearchRUCInSRITests(SimpleTestCase):
    """Prueba de regresión de un error real encontrado en esta sesión: el
    servicio público del SRI para buscar un RUC puede responder 200 OK con
    una página HTML de "solicitud rechazada" en vez de JSON (su firewall
    bloqueando la consulta). El código viejo llamaba a .json() sin
    protección y esto rompía la búsqueda sin ningún mensaje útil."""

    @patch('core.pos.utilities.sri.requests.get')
    def test_non_json_response_returns_a_clean_error_instead_of_crashing(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError('not json')))

        result = SRI().search_ruc_in_sri('1002376026001')

        self.assertIn('error', result)

    @patch('core.pos.utilities.sri.requests.get')
    def test_network_failure_returns_a_clean_error_instead_of_raising(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError('sin conexión')

        result = SRI().search_ruc_in_sri('1002376026001')

        self.assertIn('error', result)

    @patch('core.pos.utilities.sri.requests.get')
    def test_valid_json_response_is_returned_as_is(self, mock_get):
        mock_get.return_value = Mock(status_code=200, json=Mock(return_value={'razonSocial': 'CLIENTE DE PRUEBA'}))

        result = SRI().search_ruc_in_sri('1002376026001')

        self.assertEqual(result, {'razonSocial': 'CLIENTE DE PRUEBA'})


class TenantFixtureTestCase(FastTenantTestCase):
    """Base con los datos mínimos (empresa, cliente, productos) para probar
    lógica de negocio dentro del esquema de un tenant de prueba."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        plan = Plan.objects.create(name='Plan de prueba', quantity=0)
        company = Company(
            ruc='1234567890001',
            business_name='Empresa de Prueba S.A.',
            tradename='Empresa de Prueba',
            main_address='Dirección de prueba',
            establishment_address='Dirección de prueba',
            establishment_code='001',
            issuing_point_code='001',
            special_taxpayer='0',
            mobile='0999999999',
            phone='022222222',
            email='pruebas@test.com',
            website='pruebas.test.com',
            iva=Decimal('15.00'),
            electronic_signature_key='x',
            email_host_user='x',
            email_host_password='x',
            schema_name=cls.get_test_schema_name(),
            scheme=cls.tenant,
            plan=plan,
        )
        # Company.save() normalmente crea un esquema de tenant nuevo como
        # efecto secundario (el flujo real de alta de una empresa).
        # bulk_create se lo salta para que la Company solo se adjunte al
        # esquema de prueba que FastTenantTestCase ya preparó.
        Company.objects.bulk_create([company])
        cls.company = Company.objects.get(pk=company.pk)

        cls.employee = User.objects.create(username='empleado_prueba')
        client_user = User.objects.create(username='0999999999')
        cls.client_obj = Client.objects.create(
            user=client_user,
            dni='9999999999',
            mobile='0988888888',
            address='Dirección del cliente',
        )
        category = Category.objects.create(name='General')
        cls.taxed_product = Product.objects.create(
            name='Producto con IVA', code='TEST-TAX', category=category,
            price=Decimal('10.00'), pvp=Decimal('11.50'), with_tax=True,
        )
        cls.exempt_product = Product.objects.create(
            name='Producto sin IVA', code='TEST-EXE', category=category,
            price=Decimal('20.00'), pvp=Decimal('20.00'), with_tax=False,
        )


class QuotationCalculationTests(TenantFixtureTestCase):
    """El cálculo de subtotal, descuento e IVA es la parte que, si falla,
    hace que se cobre de más o de menos sin que nadie lo note."""

    def _new_quotation(self, sequence):
        receipt = Receipt.objects.create(
            voucher_type=VOUCHER_TYPE[3][0],
            establishment_code='001',
            issuing_point_code='001',
            sequence=sequence,
        )
        quotation = Quotation()
        quotation.client = self.client_obj
        quotation.company = self.company
        quotation.employee = self.employee
        quotation.iva = Decimal('0.15')
        quotation.receipt = receipt
        quotation.voucher_number = quotation.generate_voucher_number()
        quotation.voucher_number_full = quotation.get_voucher_number_full()
        quotation.save()
        return quotation

    def test_subtotal_iva_and_total_with_mixed_taxed_and_exempt_products(self):
        quotation = self._new_quotation(sequence=0)
        QuotationDetail.objects.create(quotation=quotation, product=self.taxed_product, cant=2, price=Decimal('10.00'), dscto=0)
        QuotationDetail.objects.create(quotation=quotation, product=self.exempt_product, cant=1, price=Decimal('20.00'), dscto=0)

        quotation.recalculate_invoice()

        self.assertEqual(quotation.subtotal_12, Decimal('20.00'))
        self.assertEqual(quotation.subtotal_0, Decimal('20.00'))
        self.assertEqual(quotation.total_iva, Decimal('3.00'))  # 15% de 20.00
        self.assertEqual(quotation.total, Decimal('43.00'))

    def test_discount_is_applied_before_calculating_iva(self):
        # 10% de descuento sobre una línea de $100 con impuesto: la base
        # gravable debe bajar a $90 ANTES de calcularle el 15% de IVA, no
        # después de calcular el IVA sobre los $100 completos.
        quotation = self._new_quotation(sequence=10)
        QuotationDetail.objects.create(quotation=quotation, product=self.taxed_product, cant=10, price=Decimal('10.00'), dscto=Decimal('0.10'))

        quotation.recalculate_invoice()

        self.assertEqual(quotation.subtotal_12, Decimal('90.00'))
        self.assertEqual(quotation.total_dscto, Decimal('10.00'))
        self.assertEqual(quotation.total_iva, Decimal('13.50'))
        self.assertEqual(quotation.total, Decimal('103.50'))

    def test_quotation_with_no_products_totals_zero(self):
        quotation = self._new_quotation(sequence=20)

        quotation.recalculate_invoice()

        self.assertEqual(quotation.total, Decimal('0.00'))
        self.assertEqual(quotation.total_iva, Decimal('0.00'))


class ReceiptSequenceTests(TenantFixtureTestCase):
    """El número secuencial (ej. 001-001-000000005) es lo que hace válido
    legalmente a un comprobante: nunca debe repetirse ni saltarse."""

    def test_voucher_sequence_increments_by_one_per_saved_quotation(self):
        receipt = Receipt.objects.create(
            voucher_type=VOUCHER_TYPE[3][0],
            establishment_code='002',
            issuing_point_code='001',
            sequence=5,
        )

        first = Quotation()
        first.client = self.client_obj
        first.company = self.company
        first.employee = self.employee
        first.iva = Decimal('0.15')
        first.receipt = receipt
        first.voucher_number = first.generate_voucher_number()
        first.voucher_number_full = first.get_voucher_number_full()
        first.save()

        second = Quotation()
        second.client = self.client_obj
        second.company = self.company
        second.employee = self.employee
        second.iva = Decimal('0.15')
        second.receipt = receipt
        second.voucher_number = second.generate_voucher_number()
        second.voucher_number_full = second.get_voucher_number_full()
        second.save()

        self.assertEqual(first.voucher_number, '000000006')
        self.assertEqual(second.voucher_number, '000000007')
        self.assertEqual(first.voucher_number_full, '002-001-000000006')

        receipt.refresh_from_db()
        self.assertEqual(receipt.sequence, 7)

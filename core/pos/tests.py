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


# ---------------------------------------------------------------------------
# Compras: validación del XML del proveedor, IVA y cierre de caja
# ---------------------------------------------------------------------------
from datetime import date as _date

from core.pos.models import CashRegister, DebtsPay, Provider, Purchase, PurchaseDetail
from core.pos.utilities.purchase_xml_import import InvalidPurchaseXMLError, parse_supplier_invoice_xml


class PurchaseXMLValidationTests(SimpleTestCase):
    """El XML del proveedor queda registrado como historial de la compra (y
    alimenta el ATS): un archivo alterado o inconsistente se debe rechazar."""

    RUC = '1790012345001'

    def _key(self, secuencial='000000123', cod_doc='01', ruc=None):
        today = _date.today().strftime('%d%m%Y')
        body = f'{today}{cod_doc}{ruc or self.RUC}1001001{secuencial}12345678' + '1'
        return body + SRI().compute_mod11(body)

    def _xml(self, key=None, total='28.00', subtotal='25.00', estado='AUTORIZADO', secuencial='000000123', ruc=None):
        key = key or self._key()
        fecha = _date.today().strftime('%d/%m/%Y')
        factura = (
            '<factura id="comprobante" version="1.0.0"><infoTributaria><ambiente>2</ambiente>'
            f'<razonSocial>Proveedor</razonSocial><ruc>{ruc or self.RUC}</ruc><claveAcceso>{key}</claveAcceso><codDoc>01</codDoc>'
            f'<estab>001</estab><ptoEmi>001</ptoEmi><secuencial>{secuencial}</secuencial></infoTributaria>'
            f'<infoFactura><fechaEmision>{fecha}</fechaEmision><totalSinImpuestos>{subtotal}</totalSinImpuestos>'
            '<totalConImpuestos><totalImpuesto><codigo>2</codigo><codigoPorcentaje>4</codigoPorcentaje><baseImponible>20.00</baseImponible><valor>3.00</valor></totalImpuesto></totalConImpuestos>'
            f'<importeTotal>{total}</importeTotal></infoFactura><detalles>'
            '<detalle><codigoPrincipal>A1</codigoPrincipal><descripcion>Con IVA</descripcion><cantidad>2</cantidad><precioUnitario>10.00</precioUnitario><descuento>0.00</descuento><precioTotalSinImpuesto>20.00</precioTotalSinImpuesto>'
            '<impuestos><impuesto><codigo>2</codigo><codigoPorcentaje>4</codigoPorcentaje><tarifa>15</tarifa></impuesto></impuestos></detalle>'
            '<detalle><codigoPrincipal>B2</codigoPrincipal><descripcion>Tarifa 0</descripcion><cantidad>1</cantidad><precioUnitario>5.00</precioUnitario><descuento>0.00</descuento><precioTotalSinImpuesto>5.00</precioTotalSinImpuesto>'
            '<impuestos><impuesto><codigo>2</codigo><codigoPorcentaje>0</codigoPorcentaje><tarifa>0</tarifa></impuesto></impuestos></detalle>'
            '</detalles></factura>'
        )
        return (
            f'<autorizacion><estado>{estado}</estado><numeroAutorizacion>{key}</numeroAutorizacion>'
            f'<fechaAutorizacion>2026-10-05T10:00:00-05:00</fechaAutorizacion><ambiente>PRODUCCION</ambiente>'
            f'<comprobante><![CDATA[{factura}]]></comprobante></autorizacion>'
        )

    def test_valid_xml_is_read_with_vat_per_line_and_authorization(self):
        parsed = parse_supplier_invoice_xml(self._xml())
        info = parsed['info']
        self.assertEqual(info['invoice_number'], '001001000000123')
        self.assertEqual(info['clave_acceso'], self._key())
        self.assertTrue(info['authorized'])
        self.assertEqual((info['total'], info['total_iva']), (28.0, 3.0))
        self.assertEqual([(l['tax'], l['iva_percent']) for l in parsed['lines']], [('iva', Decimal('15.00')), ('0', Decimal('0.00'))])

    def test_altered_access_key_check_digit_is_rejected(self):
        key = self._key()
        tampered = key[:48] + str((int(key[48]) + 1) % 10)
        with self.assertRaisesMessage(InvalidPurchaseXMLError, 'dígito verificador'):
            parse_supplier_invoice_xml(self._xml(key=tampered))

    def test_key_ruc_must_match_the_issuer(self):
        with self.assertRaisesMessage(InvalidPurchaseXMLError, 'RUC'):
            parse_supplier_invoice_xml(self._xml(key=self._key(ruc='1790099999001')))

    def test_invoice_number_must_match_its_access_key(self):
        with self.assertRaises(InvalidPurchaseXMLError):
            parse_supplier_invoice_xml(self._xml(key=self._key(secuencial='000000124'), secuencial='000000123'))

    def test_declared_totals_must_add_up(self):
        with self.assertRaisesMessage(InvalidPurchaseXMLError, 'inconsistente'):
            parse_supplier_invoice_xml(self._xml(total='99.00'))
        with self.assertRaisesMessage(InvalidPurchaseXMLError, 'inconsistente'):
            parse_supplier_invoice_xml(self._xml(subtotal='40.00'))

    def test_unauthorized_voucher_is_rejected(self):
        with self.assertRaisesMessage(InvalidPurchaseXMLError, 'no está autorizado'):
            parse_supplier_invoice_xml(self._xml(estado='NO AUTORIZADO'))

    def test_a_line_discount_registers_the_net_unit_price(self):
        xml = self._xml().replace(
            '<precioUnitario>10.00</precioUnitario><descuento>0.00</descuento><precioTotalSinImpuesto>20.00</precioTotalSinImpuesto>',
            '<precioUnitario>11.00</precioUnitario><descuento>2.00</descuento><precioTotalSinImpuesto>20.00</precioTotalSinImpuesto>')
        parsed = parse_supplier_invoice_xml(xml)
        self.assertEqual(parsed['lines'][0]['price'], Decimal('10.00'))  # 20.00 / 2, no los 11.00 brutos
        self.assertTrue(any('descuento' in w for w in parsed['warnings']))


class PurchaseTotalsAndCashTests(TenantFixtureTestCase):
    def _purchase(self, payment_type='efectivo', created_by=None):
        n = Provider.objects.count()
        provider = Provider.objects.create(name=f'Prov {n}', ruc=f'17900000{n:05d}', mobile=f'09900{n:05d}', email=f'p{n}@t.com')
        purchase = Purchase.objects.create(number=f'00100100{Purchase.objects.count():07d}', provider=provider, payment_type=payment_type, created_by=created_by)
        PurchaseDetail.objects.create(purchase=purchase, product=self.taxed_product, cant=2, price=Decimal('10.00'), subtotal=Decimal('20.00'), tax_type='iva', iva_percent=Decimal('15.00'))
        PurchaseDetail.objects.create(purchase=purchase, product=self.exempt_product, cant=1, price=Decimal('5.00'), subtotal=Decimal('5.00'), tax_type='exento')
        purchase.calculate_invoice()
        purchase.refresh_from_db()
        return purchase

    def test_totals_split_bases_by_tax_type_and_add_vat(self):
        purchase = self._purchase()
        self.assertEqual((purchase.subtotal_iva, purchase.subtotal_exempt, purchase.subtotal_0), (Decimal('20.00'), Decimal('5.00'), Decimal('0.00')))
        self.assertEqual((purchase.subtotal, purchase.total_iva, purchase.total), (Decimal('25.00'), Decimal('3.00'), Decimal('28.00')))

    def test_cash_purchase_reduces_expected_cash_only_for_its_cashier(self):
        self._purchase('efectivo', created_by=self.employee)
        self._purchase('credito', created_by=self.employee)  # a crédito: no sale efectivo
        mine = CashRegister.compute_breakdown(_date.today(), user=self.employee, opening_amount=100)
        self.assertEqual(mine['compras_efectivo'], 28.0)
        self.assertEqual(mine['expected_cash'], 72.0)
        other = CashRegister.compute_breakdown(_date.today(), user=self.client_obj.user, opening_amount=100)
        self.assertEqual(other['compras_efectivo'], 0.0)
        everyone = CashRegister.compute_breakdown(_date.today(), opening_amount=100)
        self.assertEqual(everyone['compras_efectivo'], 28.0)


# ---------------------------------------------------------------------------
# Retenciones emitidas a proveedores (comprobante 07)
# ---------------------------------------------------------------------------
from core.pos.models import Receipt as _Receipt, RetentionConcept, SupplierRetention, SupplierRetentionDetail
from core.pos.retention_catalog import IVA_CONCEPTS, RENTA_CONCEPTS
from core.pos.utilities.xsd import validate_xml


class RetentionCatalogTests(SimpleTestCase):
    """El catálogo se siembra desde el Catálogo ATS oficial: sus códigos son los
    que el SRI valida, así que no pueden repetirse ni salirse del campo XML."""

    def test_renta_codes_are_unique_and_fit_the_xml_field(self):
        codes = [c[0] for c in RENTA_CONCEPTS]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(1 <= len(code) <= 5 for code in codes))  # codigoRetencion: máx. 5 caracteres

    def test_iva_codes_match_the_official_table_20(self):
        # Tabla 20 de la Ficha Técnica offline v2.34: porcentaje -> código.
        self.assertEqual({code: pct for code, _, pct, _ in IVA_CONCEPTS}, {'9': 10.0, '10': 20.0, '1': 30.0, '11': 50.0, '2': 70.0, '3': 100.0, '7': 0.0})

    def test_percentages_that_depend_on_the_case_are_left_for_manual_entry(self):
        by_code = {c[0]: c for c in RENTA_CONCEPTS}
        self.assertIsNone(by_code['310'][2])  # "1 /0 según resolución"
        self.assertIsNone(by_code['346'][2])  # "varios porcentajes"
        self.assertEqual(by_code['312'][2], 2.0)


class RetentionXSDTests(SimpleTestCase):
    """El XML se valida contra el XSD oficial ANTES de firmar y enviar."""

    def _xml(self, secuencial='<secuencial>000000151</secuencial>'):
        return (
            '<comprobanteRetencion id="comprobante" version="2.0.0"><infoTributaria><ambiente>1</ambiente><tipoEmision>1</tipoEmision>'
            '<razonSocial>Empresa</razonSocial><ruc>0603164773001</ruc><claveAcceso>' + '1' * 49 + '</claveAcceso><codDoc>07</codDoc>'
            '<estab>001</estab><ptoEmi>001</ptoEmi>' + secuencial + '<dirMatriz>Dir</dirMatriz></infoTributaria>'
            '<infoCompRetencion><fechaEmision>05/10/2026</fechaEmision><tipoIdentificacionSujetoRetenido>04</tipoIdentificacionSujetoRetenido>'
            '<parteRel>NO</parteRel><razonSocialSujetoRetenido>Proveedor</razonSocialSujetoRetenido>'
            '<identificacionSujetoRetenido>1790012345001</identificacionSujetoRetenido><periodoFiscal>10/2026</periodoFiscal></infoCompRetencion>'
            '<docsSustento><docSustento><codSustento>01</codSustento><codDocSustento>01</codDocSustento><numDocSustento>001001000000321</numDocSustento>'
            '<fechaEmisionDocSustento>05/10/2026</fechaEmisionDocSustento><pagoLocExt>01</pagoLocExt><totalSinImpuestos>20.00</totalSinImpuestos>'
            '<importeTotal>23.00</importeTotal><impuestosDocSustento><impuestoDocSustento><codImpuestoDocSustento>2</codImpuestoDocSustento>'
            '<codigoPorcentaje>4</codigoPorcentaje><baseImponible>20.00</baseImponible><tarifa>15.00</tarifa><valorImpuesto>3.00</valorImpuesto>'
            '</impuestoDocSustento></impuestosDocSustento><retenciones><retencion><codigo>1</codigo><codigoRetencion>312</codigoRetencion>'
            '<baseImponible>20.00</baseImponible><porcentajeRetener>2.00</porcentajeRetener><valorRetenido>0.40</valorRetenido></retencion></retenciones>'
            '<pagos><pago><formaPago>01</formaPago><total>23.00</total></pago></pagos></docSustento></docsSustento></comprobanteRetencion>'
        )

    def test_a_well_formed_retention_passes_the_official_schema(self):
        validate_xml(self._xml(), 'ComprobanteRetencion_V2.0.0.xsd')

    def test_a_retention_missing_a_required_field_is_rejected_with_a_clear_message(self):
        with self.assertRaisesMessage(ValueError, 'no cumple el esquema oficial'):
            validate_xml(self._xml(secuencial=''), 'ComprobanteRetencion_V2.0.0.xsd')

    def test_a_malformed_sequential_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_xml(self._xml(secuencial='<secuencial>151</secuencial>'), 'ComprobanteRetencion_V2.0.0.xsd')


class SupplierRetentionFlowTests(TenantFixtureTestCase):
    def _purchase(self):
        provider = Provider.objects.create(name='Prov Ret', ruc='1790012345001', mobile='0990000011', email='r@t.com')
        purchase = Purchase.objects.create(
            number='001001000000321', provider=provider, payment_type='credito', issue_date=_date.today(),
            authorization_number='3' * 49, tax_support='01',
        )
        PurchaseDetail.objects.create(purchase=purchase, product=self.taxed_product, cant=2, price=Decimal('10.00'), subtotal=Decimal('20.00'), tax_type='iva', iva_percent=Decimal('15.00'))
        purchase.calculate_invoice()
        DebtsPay.objects.create(purchase=purchase, debt=purchase.total, saldo=purchase.total)
        purchase.refresh_from_db()
        return purchase

    def test_the_series_must_be_configured_by_hand_and_the_system_continues_from_it(self):
        with self.assertRaisesMessage(ValueError, 'Configura primero la secuencia'):
            SupplierRetention.get_receipt_for(self.company)
        _Receipt.objects.create(voucher_type='07', establishment_code='001', issuing_point_code='001', sequence=150)
        receipt = SupplierRetention.get_receipt_for(self.company)
        retention = SupplierRetention(company=self.company, receipt=receipt)
        self.assertEqual(retention.generate_voucher_number(), '000000151')

    def test_a_retention_lowers_the_payable_without_being_cash_paid(self):
        purchase = self._purchase()
        receipt = _Receipt.objects.create(voucher_type='07', establishment_code='001', issuing_point_code='001', sequence=0)
        retention = SupplierRetention.objects.create(
            company=self.company, purchase=purchase, provider=purchase.provider, receipt=receipt,
            voucher_number='000000001', voucher_number_full='001-001-000000001')
        concept = RetentionConcept.objects.get(kind='renta', code='312')
        SupplierRetentionDetail.objects.create(retention=retention, concept=concept, base=Decimal('20.00'), percentage=Decimal('2.00'), value=Decimal('0.40'))
        retention.calculate_totals()
        retention.apply_to_debts_pay()
        self.assertEqual(DebtsPay.objects.get(purchase=purchase).saldo, purchase.total - Decimal('0.40'))
        self.assertEqual(CashRegister.compute_breakdown(_date.today(), opening_amount=0)['pagos_efectivo'], 0.0)

    def test_an_authorized_retention_cannot_be_deleted(self):
        purchase = self._purchase()
        receipt = _Receipt.objects.create(voucher_type='07', establishment_code='001', issuing_point_code='001', sequence=0)
        retention = SupplierRetention.objects.create(
            company=self.company, purchase=purchase, provider=purchase.provider, receipt=receipt,
            voucher_number='000000002', voucher_number_full='001-001-000000002', status='authorized')
        with self.assertRaisesMessage(ValueError, 'autorizada'):
            retention.delete()


class SRIConnectionErrorMessageTests(SimpleTestCase):
    """Un corte de conexión con el SRI debe explicarse en claro, no mostrar el
    texto técnico de la librería."""

    def test_a_timeout_is_explained_and_says_the_voucher_was_not_lost(self):
        from core.pos.utilities.sri import describe_sri_error
        message = describe_sri_error(Exception('<urlopen error timed out>'))
        self.assertIn('no respondió a tiempo', message)
        self.assertIn('Sin Autorizar', message)
        self.assertIn('<urlopen error timed out>', message)  # el detalle técnico se conserva para soporte

    def test_a_refused_connection_is_explained(self):
        from core.pos.utilities.sri import describe_sri_error
        self.assertIn('No se pudo conectar', describe_sri_error(Exception('<urlopen error [Errno 111] Connection refused>')))

    def test_other_errors_are_left_untouched(self):
        from core.pos.utilities.sri import describe_sri_error
        self.assertEqual(describe_sri_error(Exception('ERROR SECUENCIAL REGISTRADO')), 'ERROR SECUENCIAL REGISTRADO')


class AgentResolutionNumberTests(SimpleTestCase):
    """<agenteRetencion> lleva el número de la resolución sin ceros a la
    izquierda (ficha técnica del SRI, Anexo 21)."""

    def _company(self, resolution):
        from core.tenant.models import Company as C
        return C(retention_agent_resolution=resolution)

    def test_leading_zeros_are_removed(self):
        self.assertEqual(self._company('00000284').get_agent_resolution(), '284')
        self.assertEqual(self._company('284').get_agent_resolution(), '284')

    def test_non_digits_are_ignored_and_empty_stays_empty(self):
        self.assertEqual(self._company('NAC-0284').get_agent_resolution(), '284')
        self.assertEqual(self._company('').get_agent_resolution(), '')

    def test_invoices_keep_the_previous_value_when_the_number_is_not_registered_yet(self):
        # Empresas que ya facturaban como agente: no cambia de un día a otro.
        self.assertEqual(self._company('').get_agent_resolution_for_xml(), '1')
        self.assertEqual(self._company('00000284').get_agent_resolution_for_xml(), '284')


class ElectronicSignatureValidityTests(SimpleTestCase):
    """El SRI rechaza con "FIRMA INVALIDA" todo comprobante firmado fuera de la
    vigencia del certificado: se revisa antes de firmar y de enviar."""

    PASSWORD = 'clave-de-prueba'

    def _p12(self, start, end):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'EMPRESA DE PRUEBA')])
        certificate = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(start).not_valid_after(end).sign(key, hashes.SHA256())
        )
        return pkcs12.serialize_key_and_certificates(b'firma', key, certificate, None, serialization.BestAvailableEncryption(self.PASSWORD.encode()))

    def test_a_valid_certificate_has_no_problem(self):
        from datetime import datetime, timedelta, timezone
        from core.pos.utilities.sri import signature_validity_problem
        now = datetime.now(timezone.utc)
        data = self._p12(now - timedelta(days=30), now + timedelta(days=300))
        self.assertIsNone(signature_validity_problem(data, self.PASSWORD))

    def test_an_expired_certificate_is_reported_clearly(self):
        from datetime import datetime, timedelta, timezone
        from core.pos.utilities.sri import signature_validity_problem
        now = datetime.now(timezone.utc)
        data = self._p12(now - timedelta(days=400), now - timedelta(days=5))
        message = signature_validity_problem(data, self.PASSWORD)
        self.assertIn('VENCIÓ', message)
        self.assertIn('Editar Compañía', message)

    def test_a_certificate_that_has_not_started_is_reported(self):
        from datetime import datetime, timedelta, timezone
        from core.pos.utilities.sri import signature_validity_problem
        now = datetime.now(timezone.utc)
        data = self._p12(now + timedelta(days=2), now + timedelta(days=400))
        self.assertIn('todavía no está vigente', signature_validity_problem(data, self.PASSWORD))

    def test_an_unreadable_certificate_is_left_to_the_signing_step_to_report(self):
        from core.pos.utilities.sri import signature_validity_problem
        self.assertIsNone(signature_validity_problem(b'no es un p12', self.PASSWORD))


class SRIRejectionMessageTests(SimpleTestCase):
    """Los rechazos del SRI se traducen a un mensaje que el usuario entienda."""

    def test_signature_outside_validity_period_is_explained(self):
        from core.pos.utilities.sri import describe_sri_rejection
        text = describe_sri_rejection([{
            'identificador': '39', 'mensaje': 'FIRMA INVALIDA',
            'informacionAdicional': 'La fecha de la firma está fuera del periodo de validez del certificado', 'tipo': 'ERROR'}])
        self.assertIn('VENCIDA', text)
        self.assertIn('Editar Compañía', text)

    def test_other_signature_rejection_points_to_ruc_and_password(self):
        from core.pos.utilities.sri import describe_sri_rejection
        text = describe_sri_rejection([{'identificador': '39', 'mensaje': 'FIRMA INVALIDA', 'informacionAdicional': 'Firma no corresponde al RUC', 'tipo': 'ERROR'}])
        self.assertIn('RUC', text)
        self.assertIn('clave', text)

    def test_other_rejections_keep_sri_wording_and_code(self):
        from core.pos.utilities.sri import describe_sri_rejection
        text = describe_sri_rejection([{'identificador': '35', 'mensaje': 'ARCHIVO NO CUMPLE ESTRUCTURA XML', 'informacionAdicional': 'cvc-complex-type', 'tipo': 'ERROR'}])
        self.assertIn('ARCHIVO NO CUMPLE ESTRUCTURA XML', text)
        self.assertIn('35', text)

    def test_error_text_accepts_strings_and_rejection_dicts(self):
        from core.pos.utilities.sri import error_text
        self.assertEqual(error_text('hola'), 'hola')
        self.assertEqual(error_text({'errors': [], 'message': 'claro'}), 'claro')
        self.assertEqual(error_text({'errors': []}, 'por defecto'), 'por defecto')
        self.assertEqual(error_text(None, 'por defecto'), 'por defecto')

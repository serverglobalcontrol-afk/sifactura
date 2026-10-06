"""Pruebas del módulo de Contabilidad.

Lo más delicado: que cada asiento automático CUADRE (Debe = Haber), que
sincronizar dos veces no duplique nada, que los tickets no se contabilicen,
que una venta anulada se trate bien con y sin nota de crédito, que un período
cerrado quede intacto y que NINGÚN error contable pueda tumbar una venta.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db.models import Sum
from django.test import SimpleTestCase

from core.contabilidad import activation
from core.contabilidad.hooks import sync
from core.contabilidad.models import (
    Account, AccountingConfig, AccountingPeriod, AccountMapping, BankAccount, BankAlias, JournalEntry, TypeAccountMapping,
)
from core.contabilidad.services import posting
from core.contabilidad.services.accounts import create_bank_account
from core.contabilidad.services.posting import Line
from core.pos.models import (
    CashRegister, CreditNote, CreditNoteDetail, CtasCollect, Expenses, Income, PaymentsCtaCollect, Receipt, Retention,
    Sale, SaleDetail, TypeExpense, TypeIncome, VOUCHER_TYPE, INVOICE_STATUS,
)
from core.pos.tests import TenantFixtureTestCase
from core.security.models import Module
from core.tenant.models import Company

GATE = 'core.contabilidad.services.gate.get_company'


class AccountingTestCase(TenantFixtureTestCase):
    """Empresa que SÍ lleva contabilidad, con el plan de cuentas base y la
    contabilidad iniciada hace 30 días."""

    def setUp(self):
        super().setUp()
        company = Company.objects.get(pk=self.company.pk)
        company.obligated_accounting = 'SI'
        patcher = patch(GATE, return_value=company)
        patcher.start()
        self.addCleanup(patcher.stop)
        activation.seed_chart_of_accounts()
        AccountingConfig.objects.all().delete()
        AccountingConfig.objects.create(pk=1, start_date=date.today() - timedelta(days=30))
        self.seq = 0

    # ---- helpers ----
    def acc(self, role):
        return AccountMapping.objects.get(role=role).account

    def balance(self, role):
        """Saldo (Debe - Haber) de la cuenta de un rol, solo asientos vigentes."""
        from core.contabilidad.models import JournalEntryLine
        agg = JournalEntryLine.objects.filter(account=self.acc(role), entry__status='posted').aggregate(d=Sum('debit'), c=Sum('credit'))
        return (agg['d'] or Decimal('0')) - (agg['c'] or Decimal('0'))

    def entry_for(self, kind, pk):
        return JournalEntry.objects.filter(source_key=f'{kind}:{pk}').first()

    def assert_balanced(self, entry):
        self.assertEqual(entry.total_debit, entry.total_credit)
        self.assertGreater(entry.total_debit, 0)

    def make_sale(self, voucher_type='01', payment_type='efectivo', transfer_bank=None):
        self.seq += 1
        receipt, _ = Receipt.objects.get_or_create(voucher_type=voucher_type, establishment_code='001', issuing_point_code='001', defaults={'sequence': 0})
        sale = Sale(
            company=self.company, client=self.client_obj, receipt=receipt, employee=self.employee,
            voucher_number=str(self.seq).zfill(9), voucher_number_full=f'001-001-{self.seq:09d}',
            payment_type=payment_type, iva=Decimal('0.15'), date_joined=date.today(), transfer_bank=transfer_bank,
        )
        sale.save()
        SaleDetail.objects.create(sale=sale, product=self.taxed_product, cant=2, price=Decimal('10.00'), dscto=0)
        SaleDetail.objects.create(sale=sale, product=self.exempt_product, cant=1, price=Decimal('20.00'), dscto=0)
        sale.recalculate_invoice()
        return Sale.objects.get(pk=sale.pk)

    def make_credit_note(self, sale):
        receipt, _ = Receipt.objects.get_or_create(voucher_type=VOUCHER_TYPE[1][0], establishment_code='001', issuing_point_code='001', defaults={'sequence': 0})
        self.seq += 1
        nc = CreditNote(
            company=self.company, sale=sale, receipt=receipt, voucher_number=str(self.seq).zfill(9),
            voucher_number_full=f'001-001-{self.seq:09d}', iva=Decimal('0.15'), refund_method='cash',
            motive='Prueba', created_by=self.employee,
        )
        nc.save()
        for d in sale.saledetail_set.all():
            CreditNoteDetail.objects.create(credit_note=nc, sale_detail=d, product=d.product, cant=d.cant, price=d.price, dscto=0)
        nc.calculate_detail()
        nc.calculate_invoice()
        return CreditNote.objects.get(pk=nc.pk)


class ActivationTests(TenantFixtureTestCase):
    def test_activating_creates_chart_config_and_menu_modules(self):
        company = Company.objects.get(pk=self.company.pk)
        company.obligated_accounting = 'SI'
        activation.sync_company_accounting(company)

        self.assertTrue(AccountingConfig.objects.exists())
        self.assertTrue(Account.objects.filter(code='1.1.01.01').exists())
        self.assertEqual(AccountMapping.objects.count(), len(activation.chart.DEFAULT_ROLE_ACCOUNTS))
        self.assertTrue(Module.objects.filter(url='/contabilidad/entry/').exists())

    def test_activating_twice_does_not_duplicate_anything(self):
        company = Company.objects.get(pk=self.company.pk)
        company.obligated_accounting = 'SI'
        activation.sync_company_accounting(company)
        accounts, modules = Account.objects.count(), Module.objects.filter(url__startswith='/contabilidad/').count()
        activation.sync_company_accounting(company)
        self.assertEqual(Account.objects.count(), accounts)
        self.assertEqual(Module.objects.filter(url__startswith='/contabilidad/').count(), modules)

    def test_deactivating_hides_menu_but_keeps_accounting_data(self):
        company = Company.objects.get(pk=self.company.pk)
        company.obligated_accounting = 'SI'
        activation.sync_company_accounting(company)
        company.obligated_accounting = 'NO'
        activation.sync_company_accounting(company)

        self.assertFalse(Module.objects.filter(url__startswith='/contabilidad/').exists())
        self.assertTrue(Account.objects.exists())

    def test_company_that_does_not_keep_accounting_posts_nothing(self):
        # Sin parchear el gate: la empresa de prueba tiene obligated_accounting='NO'.
        activation.seed_chart_of_accounts()
        AccountingConfig.objects.get_or_create(pk=1)
        self.assertIsNone(sync('sale', 1))
        self.assertFalse(JournalEntry.objects.exists())


class SalePostingTests(AccountingTestCase):
    def test_cash_invoice_posts_balanced_entry_with_sales_vat_and_cost(self):
        sale = self.make_sale()
        self.assertEqual(posting.sync_source('sale', sale.pk), 'created')

        entry = self.entry_for('sale', sale.pk)
        self.assert_balanced(entry)
        self.assertEqual(sale.total, Decimal('43.00'))  # 20 + 20 + 3 de IVA
        self.assertEqual(self.balance('caja'), Decimal('43.00'))
        self.assertEqual(self.balance('ventas_gravadas'), Decimal('-20.00'))
        self.assertEqual(self.balance('ventas_0'), Decimal('-20.00'))
        self.assertEqual(self.balance('iva_ventas'), Decimal('-3.00'))
        # costo: 2 x $10 + 1 x $20
        self.assertEqual(self.balance('costo_ventas'), Decimal('40.00'))
        self.assertEqual(self.balance('inventario'), Decimal('-40.00'))

    def test_syncing_twice_does_not_duplicate_the_entry(self):
        sale = self.make_sale()
        self.assertEqual(posting.sync_source('sale', sale.pk), 'created')
        self.assertEqual(posting.sync_source('sale', sale.pk), 'unchanged')
        self.assertEqual(JournalEntry.objects.filter(source_key=f'sale:{sale.pk}').count(), 1)

    def test_ticket_is_never_posted(self):
        ticket = self.make_sale(voucher_type=VOUCHER_TYPE[2][0])
        self.assertEqual(posting.sync_source('sale', ticket.pk), 'skipped')
        self.assertFalse(JournalEntry.objects.exists())

    def test_credit_sale_debits_receivable(self):
        sale = self.make_sale(payment_type='credito')
        posting.sync_source('sale', sale.pk)
        self.assertEqual(self.balance('clientes'), Decimal('43.00'))
        self.assertEqual(self.balance('caja'), Decimal('0'))

    def test_transfer_sale_goes_to_the_bank_matching_the_alias(self):
        pichincha = create_bank_account('Banco Pichincha', '2200123456', 'corriente')
        BankAlias.objects.create(text='Pichincha', bank_account=pichincha)
        sale = self.make_sale(payment_type='transferencia', transfer_bank='  PICHINCHA ')
        posting.sync_source('sale', sale.pk)
        line = self.entry_for('sale', sale.pk).lines.get(account=pichincha.account)
        self.assertEqual(line.debit, Decimal('43.00'))
        self.assertEqual(line.bank_account, pichincha)

    def test_transfer_with_unknown_bank_falls_back_to_default_bank(self):
        sale = self.make_sale(payment_type='transferencia', transfer_bank='Banco que no existe')
        posting.sync_source('sale', sale.pk)
        self.assertEqual(self.balance('banco_defecto'), Decimal('43.00'))

    def test_card_sale_goes_to_card_receivable(self):
        sale = self.make_sale(payment_type='tarjeta_credito')
        posting.sync_source('sale', sale.pk)
        self.assertEqual(self.balance('tarjetas'), Decimal('43.00'))

    def test_cancelled_sale_without_credit_note_is_voided(self):
        sale = self.make_sale()
        posting.sync_source('sale', sale.pk)
        Sale.objects.filter(pk=sale.pk).update(status=INVOICE_STATUS[3][0])
        self.assertEqual(posting.sync_source('sale', sale.pk), 'voided')
        self.assertEqual(self.entry_for('sale', sale.pk).status, 'voided')
        self.assertEqual(self.balance('caja'), Decimal('0'))

    def test_cancelled_sale_with_credit_note_keeps_sale_and_credit_note_reverses_it(self):
        sale = self.make_sale()
        posting.sync_source('sale', sale.pk)
        nc = self.make_credit_note(sale)
        Sale.objects.filter(pk=sale.pk).update(status=INVOICE_STATUS[3][0])

        self.assertEqual(posting.sync_source('sale', sale.pk), 'unchanged')
        self.assertEqual(posting.sync_source('credit_note', nc.pk), 'created')
        self.assert_balanced(self.entry_for('credit_note', nc.pk))
        # Venta + nota de crédito = todo en cero (ingresos, IVA, caja, costo e inventario).
        for role in ('caja', 'iva_ventas', 'inventario', 'costo_ventas'):
            self.assertEqual(self.balance(role), Decimal('0'), role)
        self.assertEqual(self.balance('ventas_gravadas') + self.balance('ventas_0') + self.balance('devoluciones'), Decimal('0'))

    def test_sale_before_the_accounting_start_date_is_skipped(self):
        AccountingConfig.objects.update(start_date=date.today() + timedelta(days=1))
        sale = self.make_sale()
        self.assertEqual(posting.sync_source('sale', sale.pk), 'skipped')
        self.assertFalse(JournalEntry.objects.exists())

    def test_closed_period_blocks_changes(self):
        sale = self.make_sale()
        posting.sync_source('sale', sale.pk)
        AccountingPeriod.objects.create(year=date.today().year, month=date.today().month, status='closed')
        Sale.objects.filter(pk=sale.pk).update(status=INVOICE_STATUS[3][0])
        self.assertEqual(posting.sync_source('sale', sale.pk), 'blocked')
        self.assertEqual(self.entry_for('sale', sale.pk).status, 'posted')


class CollectionsAndOthersTests(AccountingTestCase):
    def _credit_sale_with_payment(self, valor='10.00', retention=None):
        sale = self.make_sale(payment_type='credito')
        cc = CtasCollect.objects.create(sale=sale, debt=sale.total, saldo=sale.total)
        pay = PaymentsCtaCollect.objects.create(created_by=self.employee, ctas_collect=cc, payment_type='cash', valor=Decimal(valor), retention=retention)
        return sale, pay

    def test_collection_debits_cash_and_credits_receivable(self):
        sale, pay = self._credit_sale_with_payment()
        posting.sync_source('sale', sale.pk)
        self.assertEqual(posting.sync_source('collection', pay.pk), 'created')
        self.assertEqual(self.balance('clientes'), Decimal('33.00'))  # 43 - 10
        self.assertEqual(self.balance('caja'), Decimal('10.00'))

    def test_payment_generated_by_a_retention_is_not_money_received(self):
        sale = self.make_sale(payment_type='credito')
        ret = Retention.objects.create(
            company=self.company, sale=sale, document_number='001-001-000000001', iva_retained=Decimal('2.00'),
            income_tax_retained=Decimal('1.00'), total_retained=Decimal('3.00'),
        )
        cc = CtasCollect.objects.create(sale=sale, debt=sale.total, saldo=sale.total)
        pay = PaymentsCtaCollect.objects.create(created_by=self.employee, ctas_collect=cc, payment_type='cash', valor=Decimal('3.00'), retention=ret)
        self.assertEqual(posting.sync_source('collection', pay.pk), 'skipped')

        posting.sync_source('sale', sale.pk)
        self.assertEqual(posting.sync_source('retention', ret.pk), 'created')
        self.assertEqual(self.balance('ret_iva'), Decimal('2.00'))
        self.assertEqual(self.balance('ret_renta'), Decimal('1.00'))
        self.assertEqual(self.balance('clientes'), Decimal('40.00'))
        self.assertEqual(self.balance('caja'), Decimal('0'))

    def test_expense_uses_its_type_account_or_the_default(self):
        kind = TypeExpense.objects.create(name='Arriendo')
        rent = Account.objects.create(code='6.1.06', name='Arriendos', account_type='gasto')
        TypeAccountMapping.objects.create(kind='expense', type_id=kind.pk, account=rent)
        expense = Expenses.objects.create(type_expense=kind, valor=Decimal('50.00'), description='Local')

        # La señal de Gastos ya lo contabilizó al guardar.
        entry = self.entry_for('expense', expense.pk)
        self.assert_balanced(entry)
        self.assertEqual(entry.lines.get(account=rent).debit, Decimal('50.00'))
        self.assertEqual(self.balance('caja'), Decimal('-50.00'))

        other = Expenses.objects.create(type_expense=TypeExpense.objects.create(name='Otros'), valor=Decimal('5.00'))
        self.assertEqual(self.entry_for('expense', other.pk).lines.get(account=self.acc('gasto_defecto')).debit, Decimal('5.00'))

    def test_editing_and_deleting_an_expense_updates_the_books(self):
        kind = TypeExpense.objects.create(name='Luz')
        expense = Expenses.objects.create(type_expense=kind, valor=Decimal('20.00'))
        expense.valor = Decimal('35.00')
        expense.save()
        self.assertEqual(self.balance('caja'), Decimal('-35.00'))
        self.assertEqual(JournalEntry.objects.filter(source_key=f'expense:{expense.pk}').count(), 1)

        pk = expense.pk
        expense.delete()
        self.assertEqual(self.entry_for('expense', pk).status, 'voided')
        self.assertEqual(self.balance('caja'), Decimal('0'))

    def test_income_by_transfer_debits_the_bank(self):
        kind = TypeIncome.objects.create(name='Aporte')
        income = Income.objects.create(type_income=kind, valor=Decimal('100.00'), payment_type='transfer')
        self.assertEqual(self.balance('banco_defecto'), Decimal('100.00'))
        self.assert_balanced(self.entry_for('income', income.pk))

    def test_cash_closing_difference_posts_surplus_or_shortage(self):
        register = CashRegister.objects.create(user=self.employee, opening_amount=Decimal('0.00'))
        register.close(counted_amount=Decimal('12.00'))  # esperado 0 -> sobrante 12
        self.assertEqual(self.balance('sobrante_caja'), Decimal('-12.00'))
        self.assertEqual(self.balance('caja'), Decimal('12.00'))

    def test_accounting_error_never_breaks_the_caller(self):
        sale = self.make_sale()
        with patch('core.contabilidad.services.posting.sync_source', side_effect=RuntimeError('boom')):
            self.assertEqual(posting.safe_sync('sale', sale.pk), 'error')
        # El hook público tampoco propaga.
        with patch('core.contabilidad.services.posting.safe_sync', side_effect=RuntimeError('boom')):
            self.assertIsNone(sync('sale', sale.pk))


class PendingSweepAndManualEntryTests(AccountingTestCase):
    def test_post_pending_creates_missing_entries_without_duplicating(self):
        sale = self.make_sale()
        expense_type = TypeExpense.objects.create(name='Varios')
        with patch(GATE, return_value=None):  # sin contabilidad activa: no se contabiliza al guardar
            expense = Expenses.objects.create(type_expense=expense_type, valor=Decimal('9.00'))
        self.assertFalse(JournalEntry.objects.exists())

        summary, errors = posting.post_pending(date.today() - timedelta(days=1), date.today())
        self.assertEqual(errors, [])
        self.assertEqual(summary['created'], 2)
        self.assertIsNotNone(self.entry_for('sale', sale.pk))
        self.assertIsNotNone(self.entry_for('expense', expense.pk))

        summary, _ = posting.post_pending(date.today() - timedelta(days=1), date.today())
        self.assertEqual(summary['created'], 0)
        self.assertEqual(summary['unchanged'], 2)

    def test_trial_balance_always_balances(self):
        from core.contabilidad.models import JournalEntryLine
        sale = self.make_sale()
        credit = self.make_sale(payment_type='credito')
        posting.sync_source('sale', sale.pk)
        posting.sync_source('sale', credit.pk)
        posting.sync_source('credit_note', self.make_credit_note(sale).pk)
        totals = JournalEntryLine.objects.filter(entry__status='posted').aggregate(d=Sum('debit'), c=Sum('credit'))
        self.assertEqual(totals['d'], totals['c'])

    def test_manual_entry_must_balance(self):
        lines = [Line(account=self.acc('caja'), debit=Decimal('10.00')), Line(account=self.acc('ingreso_defecto'), credit=Decimal('9.99'))]
        with self.assertRaises(posting.UnbalancedEntry):
            posting.create_manual_entry(date.today(), 'Descuadrado', lines)

        lines[1].credit = Decimal('10.00')
        entry = posting.create_manual_entry(date.today(), 'Cuadrado', lines)
        self.assert_balanced(entry)

    def test_only_manual_entries_can_be_voided_by_hand(self):
        sale = self.make_sale()
        posting.sync_source('sale', sale.pk)
        with self.assertRaises(ValueError):
            posting.void_manual_entry(self.entry_for('sale', sale.pk), 'no')

        lines = [Line(account=self.acc('caja'), debit=Decimal('5.00')), Line(account=self.acc('ingreso_defecto'), credit=Decimal('5.00'))]
        manual = posting.create_manual_entry(date.today(), 'Manual', lines)
        posting.void_manual_entry(manual, 'error de digitación')
        manual.refresh_from_db()
        self.assertEqual(manual.status, 'voided')

    def test_bank_deposit_moves_cash_to_the_bank(self):
        bank = create_bank_account('Banco Pichincha', '2200123456')
        posting.create_bank_move('deposit', date.today(), Decimal('100.00'), bank)
        self.assertEqual(self.balance('caja'), Decimal('-100.00'))
        from core.contabilidad.models import JournalEntryLine
        self.assertEqual(JournalEntryLine.objects.filter(account=bank.account).aggregate(d=Sum('debit'))['d'], Decimal('100.00'))

    def test_transfer_requires_a_receipt_number_and_two_different_accounts(self):
        a = create_bank_account('Banco Pichincha', '111')
        b = create_bank_account('Banco Guayaquil', '222')
        with self.assertRaises(posting.UnbalancedEntry):
            posting.create_bank_move('transfer', date.today(), Decimal('50.00'), a, other_bank_account=b)  # sin comprobante
        with self.assertRaises(posting.UnbalancedEntry):
            posting.create_bank_move('transfer', date.today(), Decimal('50.00'), a, other_bank_account=a, reference='T-1')

        entry = posting.create_bank_move('transfer', date.today(), Decimal('50.00'), a, other_bank_account=b, reference='T-1001')
        self.assert_balanced(entry)
        self.assertEqual(entry.reference, 'T-1001')
        self.assertIn('T-1001', entry.description)
        self.assertEqual(entry.lines.get(account=b.account).debit, Decimal('50.00'))
        self.assertEqual(entry.lines.get(account=a.account).credit, Decimal('50.00'))

    def test_deposit_does_not_need_a_destination_account_or_receipt(self):
        from core.contabilidad.forms import BankMoveForm
        bank = create_bank_account('Banco Pichincha', '111')
        other = create_bank_account('Banco Guayaquil', '222')
        form = BankMoveForm({'kind': 'deposit', 'date': date.today().isoformat(), 'amount': '20.00', 'bank_account': bank.pk, 'other_bank_account': other.pk})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['other_bank_account'])  # se descarta: solo la transferencia usa dos cuentas

    def test_transfer_form_rejects_missing_receipt_and_same_account(self):
        from core.contabilidad.forms import BankMoveForm
        a = create_bank_account('Banco Pichincha', '111')
        b = create_bank_account('Banco Guayaquil', '222')
        base = {'kind': 'transfer', 'date': date.today().isoformat(), 'amount': '5.00', 'bank_account': a.pk}
        self.assertIn('reference', BankMoveForm({**base, 'other_bank_account': b.pk}).errors)
        self.assertIn('other_bank_account', BankMoveForm({**base, 'other_bank_account': a.pk, 'reference': 'X'}).errors)
        self.assertIn('other_bank_account', BankMoveForm({**base, 'reference': 'X'}).errors)
        self.assertTrue(BankMoveForm({**base, 'other_bank_account': b.pk, 'reference': 'X'}).is_valid())

    def test_entries_keep_date_and_exact_creation_time(self):
        sale = self.make_sale()
        posting.sync_source('sale', sale.pk)
        entry = self.entry_for('sale', sale.pk)
        self.assertEqual(entry.date, sale.date_joined)
        self.assertIsNotNone(entry.created_at)


class ATSGeneratorTests(SimpleTestCase):
    """Generador del ATS: sin base de datos; el XML se valida con el esquema oficial."""

    def _data(self):
        from collections import OrderedDict
        from datetime import date
        from decimal import Decimal as D
        z = D('0.00')
        return {
            'year': 2026, 'month': 9, 'ruc': '0603164773001', 'name': 'EMPRESA DE PRUEBA SA',
            'purchases': [{
                'doc': 'x', 'codSustento': '01', 'tpIdProv': '01', 'idProv': '1790012345001', 'tipoComprobante': '01', 'parteRel': 'NO',
                'fechaRegistro': date(2026, 9, 5), 'establecimiento': '001', 'puntoEmision': '002', 'secuencial': 4521, 'fechaEmision': date(2026, 9, 5),
                'autorizacion': '1' * 49, 'baseNoGraIva': z, 'baseImponible': z, 'baseImpGrav': D('100.00'), 'baseImpExe': z, 'montoIce': z, 'montoIva': D('15.00'),
                'pagoLocExt': '01', 'formasDePago': ['20'],
                'retenciones': {'valRetBien10': z, 'valRetServ20': z, 'valorRetBienes': D('4.50'), 'valRetServ50': z, 'valorRetServicios': z, 'valRetServ100': z},
                'air': [{'codRetAir': '303', 'baseImpAir': D('100.00'), 'porcentajeAir': D('10.00'), 'valRetAir': D('10.00')}],
                'ret_doc': {'estab': '001', 'pto': '001', 'sec': 42, 'aut': '2' * 49, 'fecha': date(2026, 9, 6)},
            }],
            'sales': OrderedDict([(1, {
                'tpIdCliente': '07', 'idCliente': '9999999999999', 'tipoComprobante': '01', 'tipoEmision': 'E', 'numeroComprobantes': 3,
                'baseNoGraIva': z, 'baseImponible': D('10.00'), 'baseImpGrav': D('40.00'), 'montoIva': D('6.00'), 'valorRetIva': z, 'valorRetRenta': z, 'formasDePago': ['01']})]),
            'establishments': OrderedDict([('001', {'ventasEstab': D('50.00')})]), 'num_establishments': 1, 'total_sales': D('50.00'),
            'canceled': [{'tipoComprobante': '01', 'establecimiento': '001', 'puntoEmision': '001', 'secuencial': 7, 'autorizacion': '3' * 49}],
        }

    def test_a_complete_month_complies_with_the_official_schema(self):
        from core.contabilidad.services import ats
        xml = ats.render_xml(self._data())
        self.assertEqual(ats.validate_xml(xml), [])
        self.assertIn('<codigoOperativo>IVA</codigoOperativo>', xml)

    def test_a_purchase_without_authorization_is_rejected_by_the_schema(self):
        from core.contabilidad.services import ats
        data = self._data()
        data['purchases'][0]['autorizacion'] = ''
        self.assertTrue(ats.validate_xml(ats.render_xml(data)))

    def test_names_are_cleaned_to_what_the_ats_accepts(self):
        from core.contabilidad.services import ats
        self.assertEqual(ats.clean_name('Peña & Hijos, S.A. (Quito)'), 'Pena Hijos S A Quito')
        self.assertEqual(ats.clean_name('ab', minimum=5), '')

    def test_invoice_numbers_are_split_into_series_and_sequence(self):
        from core.contabilidad.services import ats
        self.assertEqual(ats.split_number('001002000004521'), ('001', '002', 4521))
        self.assertIsNone(ats.split_number('1234'))

    def test_month_ranges_and_file_names(self):
        from core.contabilidad.services import ats
        self.assertEqual(ats.months_between('2026-11', '2027-02'), [(2026, 11), (2026, 12), (2027, 1), (2027, 2)])
        self.assertEqual(ats.zip_name(2026, 9), 'AT092026')
        with self.assertRaises(ValueError):
            ats.months_between('2026-09', '2026-08')
        with self.assertRaises(ValueError):
            ats.months_between('2020-01', '2026-12')

    def test_monthly_zip_holds_the_xml_named_as_the_sri_requires(self):
        import io
        import zipfile
        from core.contabilidad.services import ats
        content = ats.monthly_zip(2026, 9, '<iva/>')
        self.assertEqual(zipfile.ZipFile(io.BytesIO(content)).namelist(), ['AT092026.xml'])
        bundle = ats.bundle_zip([('AT092026.zip', content), ('AT102026.zip', content)])
        self.assertEqual(zipfile.ZipFile(io.BytesIO(bundle)).namelist(), ['AT092026.zip', 'AT102026.zip'])

    def test_iva_retention_percentages_map_to_the_schema_fields_in_schema_order(self):
        from core.contabilidad.services import ats
        self.assertEqual(list(ats.IVA_RETENTION_FIELDS.values()), ['valRetBien10', 'valRetServ20', 'valorRetBienes', 'valRetServ50', 'valorRetServicios', 'valRetServ100'])


class FinancialStatementsTests(SimpleTestCase):
    """Armado de los estados financieros (sin base de datos)."""

    def _chart(self):
        return [
            {'id': 1, 'code': '1', 'name': 'ACTIVO', 'parent_id': None, 'type': 'activo'},
            {'id': 2, 'code': '1.1', 'name': 'Caja', 'parent_id': 1, 'type': 'activo'},
            {'id': 3, 'code': '1.2', 'name': 'Inventario', 'parent_id': 1, 'type': 'activo'},
            {'id': 4, 'code': '2', 'name': 'PASIVO', 'parent_id': None, 'type': 'pasivo'},
            {'id': 5, 'code': '2.1', 'name': 'Proveedores', 'parent_id': 4, 'type': 'pasivo'},
            {'id': 6, 'code': '3', 'name': 'PATRIMONIO', 'parent_id': None, 'type': 'patrimonio'},
            {'id': 7, 'code': '3.1', 'name': 'Capital', 'parent_id': 6, 'type': 'patrimonio'},
            {'id': 8, 'code': '4', 'name': 'INGRESOS', 'parent_id': None, 'type': 'ingreso'},
            {'id': 9, 'code': '4.1', 'name': 'Ventas', 'parent_id': 8, 'type': 'ingreso'},
            {'id': 10, 'code': '5', 'name': 'COSTOS', 'parent_id': None, 'type': 'costo'},
            {'id': 11, 'code': '5.1', 'name': 'Costo de ventas', 'parent_id': 10, 'type': 'costo'},
            {'id': 12, 'code': '6', 'name': 'GASTOS', 'parent_id': None, 'type': 'gasto'},
            {'id': 13, 'code': '6.1', 'name': 'Sueldos', 'parent_id': 12, 'type': 'gasto'},
        ]

    def _row(self, rows, name):
        return next(r for r in rows if r['name'] == name)

    def test_totals_are_added_up_and_the_check_line_shows_the_difference(self):
        from decimal import Decimal as D
        from core.contabilidad.services import statements
        # Capital 1000 (caja), compra a crédito de inventario 200, venta de 300 que costó 120 y sueldos de 50.
        balances = {2: D('1300'), 3: D('80'), 5: D('200'), 7: D('1000')}
        rows = statements.balance_sheet(self._chart(), balances, D('0'), D('130'))
        self.assertEqual(self._row(rows, 'TOTAL ACTIVO')['amount'], 1380.0)
        self.assertEqual(self._row(rows, 'TOTAL PASIVO')['amount'], 200.0)
        self.assertEqual(self._row(rows, 'TOTAL PATRIMONIO')['amount'], 1130.0)
        self.assertEqual(self._row(rows, 'TOTAL PASIVO + PATRIMONIO')['amount'], 1330.0)
        # 50 de diferencia: aquí a propósito (el sueldo no se pagó con la caja del ejemplo).
        self.assertEqual(rows[-1]['kind'], 'check')

    def test_a_consistent_book_gives_a_zero_difference(self):
        from decimal import Decimal as D
        from core.contabilidad.services import statements
        balances = {2: D('1300'), 3: D('80'), 5: D('200'), 7: D('1000')}
        rows = statements.balance_sheet(self._chart(), {2: D('1250'), 3: D('80'), 5: D('200'), 7: D('1000')}, D('0'), D('130'))
        self.assertEqual(rows[-1]['amount'], 0.0)

    def test_parents_add_up_their_children_and_zero_accounts_are_hidden(self):
        from decimal import Decimal as D
        from core.contabilidad.services import statements
        rows, total = statements.build_rows(self._chart(), {2: D('10'), 3: D('5')}, ('activo',))
        self.assertEqual(total, D('15'))
        self.assertEqual([r['code'] for r in rows], ['1', '1.1', '1.2'])
        self.assertEqual(self._row(rows, 'ACTIVO')['amount'], 15.0)
        self.assertEqual(self._row(rows, 'ACTIVO')['kind'], 'group')
        self.assertEqual(self._row(rows, 'Caja')['level'], 1)

    def test_income_statement_computes_gross_and_net_result(self):
        from decimal import Decimal as D
        from core.contabilidad.services import statements
        rows = statements.income_statement(self._chart(), {9: D('300'), 11: D('120'), 13: D('50')})
        self.assertEqual(self._row(rows, 'UTILIDAD BRUTA')['amount'], 180.0)
        self.assertEqual(rows[-1]['amount'], 130.0)

    def test_signs_follow_the_nature_of_the_account(self):
        from decimal import Decimal as D
        from core.contabilidad.services import statements
        self.assertEqual(statements.signed('activo', D('10'), D('3')), D('7'))
        self.assertEqual(statements.signed('pasivo', D('3'), D('10')), D('7'))


class BankStatementParsingTests(SimpleTestCase):
    """Lectura del estado de cuenta (Excel, CSV y PDF) sin base de datos."""

    ROWS = [
        ['Fecha', 'Descripcion', 'Documento', 'Debito', 'Credito', 'Saldo'],
        ['01/10/2026', 'DEPOSITO EN EFECTIVO', '123456', '', '100.00', '1,100.00'],
        ['02/10/2026', 'COMISION MANTENIMIENTO', '', '2.50', '', '1,097.50'],
        ['04/10/2026', 'PAGO CHEQUE 4521', '4521', '50.00', '', '1,047.50'],
    ]

    def test_money_and_dates_are_read_in_both_notations(self):
        from decimal import Decimal as D
        from datetime import date
        from core.contabilidad.services import reconciliation as rc
        self.assertEqual(rc.parse_money('1.234,56'), D('1234.56'))
        self.assertEqual(rc.parse_money('1,234.56'), D('1234.56'))
        self.assertEqual(rc.parse_money('(25.00)'), D('-25.00'))
        self.assertEqual(rc.parse_money('$ 3,10'), D('3.10'))
        self.assertIsNone(rc.parse_money('abc'))
        self.assertEqual(rc.parse_date('05/10/2026'), date(2026, 10, 5))
        self.assertEqual(rc.parse_date('2026-10-05'), date(2026, 10, 5))
        self.assertIsNone(rc.parse_date('Total'))

    def test_csv_with_semicolons_and_decimal_commas(self):
        from decimal import Decimal as D
        from core.contabilidad.services import reconciliation as rc
        text = 'Fecha;Detalle;Referencia;Debito;Credito;Saldo\n01/10/2026;DEPOSITO;123456;;100,00;1.100,00\n02/10/2026;COMISION;;2,50;;1.097,50\n'
        rows, warnings, source = rc.parse_statement_file(text.encode('utf-8'), 'estado.csv')
        self.assertEqual(source, 'csv')
        self.assertEqual([r['amount'] for r in rows], [D('100.00'), D('-2.50')])
        self.assertEqual(rows[0]['reference'], '123456')
        self.assertEqual(rows[1]['balance'], D('1097.50'))

    def test_excel_with_a_single_amount_column_and_a_type_column(self):
        import io
        from decimal import Decimal as D
        from openpyxl import Workbook
        from core.contabilidad.services import reconciliation as rc
        wb = Workbook()
        ws = wb.active
        ws.append(['Banco XYZ - estado de cuenta'])
        ws.append(['Fecha', 'Descripcion', 'Valor', 'Tipo'])
        ws.append(['01/10/2026', 'Deposito', 100, 'Credito'])
        ws.append(['02/10/2026', 'Comision', 2.5, 'Debito'])
        ws.append(['Total', '', 102.5, ''])
        buffer = io.BytesIO()
        wb.save(buffer)
        rows, warnings, source = rc.parse_statement_file(buffer.getvalue(), 'estado.xlsx')
        self.assertEqual(source, 'excel')
        self.assertEqual([r['amount'] for r in rows], [D('100.00'), D('-2.50')])
        self.assertTrue(warnings)

    def test_a_file_without_the_expected_columns_explains_what_to_do(self):
        from core.contabilidad.services import reconciliation as rc
        with self.assertRaises(rc.StatementError) as ctx:
            rc.parse_statement_file(b'a;b;c\n1;2;3\n', 'raro.csv')
        self.assertIn('Fecha', str(ctx.exception))

    def test_old_xls_and_unknown_formats_are_refused_with_a_clear_message(self):
        from core.contabilidad.services import reconciliation as rc
        for name in ('estado.xls', 'estado.docx'):
            with self.assertRaises(rc.StatementError):
                rc.parse_statement_file(b'x', name)

    def test_pdf_text_deduces_the_sign_from_the_running_balance(self):
        from decimal import Decimal as D
        from core.contabilidad.services import reconciliation as rc
        text = (
            'ESTADO DE CUENTA\n\nFecha\n\nDescripcion\n\n01/10/2026\n\nDEPOSITO EN EFECTIVO\n\n123456\n\n100.00\n\n1,100.00\n\n'
            '02/10/2026\n\nCOMISION MANTENIMIENTO\n\n2.50\n\n1,097.50\n\n04/10/2026\n\nPAGO CHEQUE 4521\n\n4521\n\n50.00\n\n1,047.50\n'
        )
        rows, warnings = rc.parse_pdf_text(text, opening_balance=D('1000.00'))
        self.assertEqual([r['amount'] for r in rows], [D('100.00'), D('-2.50'), D('-50.00')])
        self.assertEqual(rows[0]['reference'], '123456')
        self.assertEqual(rows[0]['description'], 'DEPOSITO EN EFECTIVO')
        self.assertIn('DEDUCE', warnings[0])

    def test_pdf_without_balance_falls_back_to_words_and_warns(self):
        from core.contabilidad.services import reconciliation as rc
        text = '01/10/2026 DEPOSITO EN EFECTIVO 100.00\n02/10/2026 COMISION MANTENIMIENTO 2.50\n'
        rows, warnings = rc.parse_pdf_text(text)
        self.assertEqual([float(r['amount']) for r in rows], [100.0, -2.5])
        self.assertTrue(any('descripción' in w for w in warnings))

    def test_a_pdf_without_movements_asks_for_excel_or_csv(self):
        from core.contabilidad.services import reconciliation as rc
        with self.assertRaises(rc.StatementError):
            rc.parse_pdf_text('Sin movimientos en el periodo')

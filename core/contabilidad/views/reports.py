from datetime import date, datetime
from decimal import Decimal

from django.db.models import Sum
from django.views.generic import TemplateView

from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.models import Account, BankAccount, JournalEntryLine, DEBIT_NATURE_TYPES
from core.contabilidad.views.base import json_response
from core.security.mixins import GroupModuleMixin

ZERO = Decimal('0.00')


def _dates(request):
    start = datetime.strptime(request.POST['start_date'], '%Y-%m-%d').date()
    end = datetime.strptime(request.POST['end_date'], '%Y-%m-%d').date()
    if end < start:
        raise ValueError('La fecha final no puede ser menor a la inicial.')
    return start, end


def _posted_lines():
    return JournalEntryLine.objects.filter(entry__status='posted')


def _balance(account, debit, credit):
    """Saldo según la naturaleza de la cuenta (deudora o acreedora)."""
    return (debit - credit) if account.account_type in DEBIT_NATURE_TYPES else (credit - debit)


class AccountingReportView(AccountingEnabledMixin, GroupModuleMixin, TemplateView):
    title = ''

    def build(self, request):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        try:
            if request.POST['action'] != 'search_report':
                return json_response({'error': 'No ha seleccionado ninguna opción'})
            data = self.build(request)
        except Exception as e:
            data = {'error': str(e)}
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        context['today'] = date.today().strftime('%Y-%m-%d')
        context['month_start'] = date.today().replace(day=1).strftime('%Y-%m-%d')
        return context


class JournalReportView(AccountingReportView):
    template_name = 'contabilidad/report/journal.html'
    title = 'Libro Diario'

    def build(self, request):
        start, end = _dates(request)
        rows = []
        lines = _posted_lines().filter(entry__date__range=(start, end)).select_related('entry', 'account').order_by('entry__date', 'entry__number', 'id')
        for i in lines:
            rows.append({
                'date': i.entry.date.strftime('%Y-%m-%d'),
                'number': str(i.entry),
                'description': i.description or i.entry.description,
                'account': str(i.account),
                'debit': float(i.debit),
                'credit': float(i.credit),
            })
        return rows


def ledger_rows(account, start, end):
    """Movimientos de una cuenta con saldo corriente, precedidos por una fila
    de saldo anterior."""
    before = _posted_lines().filter(account=account, entry__date__lt=start).aggregate(d=Sum('debit'), c=Sum('credit'))
    balance = _balance(account, before['d'] or ZERO, before['c'] or ZERO)
    rows = [{'date': '', 'number': '', 'description': 'SALDO ANTERIOR', 'debit': 0.0, 'credit': 0.0, 'balance': float(balance)}]
    lines = _posted_lines().filter(account=account, entry__date__range=(start, end)).select_related('entry').order_by('entry__date', 'entry__number', 'id')
    for i in lines:
        balance += _balance(account, i.debit, i.credit)
        rows.append({
            'date': i.entry.date.strftime('%Y-%m-%d'),
            'number': str(i.entry),
            'description': i.description or i.entry.description,
            'debit': float(i.debit),
            'credit': float(i.credit),
            'balance': float(balance),
        })
    return rows


class LedgerReportView(AccountingReportView):
    template_name = 'contabilidad/report/ledger.html'
    title = 'Libro Mayor'

    def build(self, request):
        start, end = _dates(request)
        account = Account.objects.get(pk=request.POST['account'])
        return ledger_rows(account, start, end)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['accounts'] = Account.objects.filter(accepts_movement=True).order_by('code')
        return context


class BankReportView(AccountingReportView):
    template_name = 'contabilidad/report/bank.html'
    title = 'Libro de Banco'

    def build(self, request):
        start, end = _dates(request)
        bank = BankAccount.objects.select_related('account').get(pk=request.POST['bank_account'])
        return ledger_rows(bank.account, start, end)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['banks'] = BankAccount.objects.select_related('account').order_by('bank_name', 'number')
        return context


class TrialBalanceReportView(AccountingReportView):
    template_name = 'contabilidad/report/trial.html'
    title = 'Balance de Comprobación'

    def build(self, request):
        start, end = _dates(request)
        before = {
            r['account']: r for r in _posted_lines().filter(entry__date__lt=start).values('account').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        during = {
            r['account']: r for r in _posted_lines().filter(entry__date__range=(start, end)).values('account').annotate(d=Sum('debit'), c=Sum('credit'))
        }
        rows = []
        for account in Account.objects.filter(pk__in=set(before) | set(during)).order_by('code'):
            b, m = before.get(account.pk), during.get(account.pk)
            initial = _balance(account, (b or {}).get('d') or ZERO, (b or {}).get('c') or ZERO)
            debit, credit = (m or {}).get('d') or ZERO, (m or {}).get('c') or ZERO
            rows.append({
                'account': str(account),
                'initial': float(initial),
                'debit': float(debit),
                'credit': float(credit),
                'final': float(initial + _balance(account, debit, credit)),
            })
        return rows

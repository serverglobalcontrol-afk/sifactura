import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.views.generic import TemplateView

from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.models import Account, BankAccount, BankStatement, BankStatementLine, JournalEntryLine
from core.contabilidad.services import reconciliation
from core.contabilidad.views.base import json_response
from core.security.mixins import GroupPermissionMixin


def _require(request, codename):
    group = request.session.get('group')
    if group is None or not group.permissions.filter(codename=codename).exists():
        raise ValueError('Tu perfil no cuenta con el permiso necesario para esta acción.')


def _money(value, label, required=True):
    text = str(value or '').strip()
    if not text:
        if required:
            raise ValueError(f'Escribe {label}.')
        return None
    parsed = reconciliation.parse_money(text)
    if parsed is None:
        raise ValueError(f'{label[0].upper()}{label[1:]} no es un valor válido.')
    return parsed


class ReconciliationListView(AccountingEnabledMixin, GroupPermissionMixin, TemplateView):
    """Listado de conciliaciones y carga de un estado de cuenta nuevo (Excel, CSV o PDF)."""
    template_name = 'contabilidad/reconciliation/list.html'
    permission_required = 'view_bankstatement'

    def post(self, request, *args, **kwargs):
        try:
            action = request.POST['action']
            if action == 'search':
                data = [i.toJSON() for i in BankStatement.objects.select_related('bank_account')]
            elif action == 'import':
                data = self.import_statement(request)
            elif action == 'delete':
                _require(request, 'delete_bankstatement')
                statement = BankStatement.objects.get(pk=request.POST['id'])
                if statement.status == 'reconciled':
                    raise ValueError('Una conciliación cerrada no se elimina: reábrela primero.')
                statement.delete()
                data = {}
            else:
                data = {'error': 'No ha seleccionado ninguna opción'}
        except Exception as e:
            data = {'error': str(e)}
        return json_response(data)

    def import_statement(self, request):
        _require(request, 'add_bankstatement')
        bank = BankAccount.objects.get(pk=request.POST['bank_account'])
        upload = request.FILES.get('file')
        if upload is None:
            raise ValueError('Elige el archivo del estado de cuenta (Excel, CSV o PDF).')
        if upload.size > 10 * 1024 * 1024:
            raise ValueError('El archivo es muy grande (máximo 10 MB).')
        opening = _money(request.POST.get('opening_balance'), 'el saldo inicial', required=False)
        year = (request.POST.get('year') or '').strip()
        if year and not (year.isdigit() and 2000 <= int(year) <= 2100):
            raise ValueError('El año debe tener 4 dígitos (por ejemplo 2026).')
        raw = upload.read()
        rows, warnings, source = reconciliation.parse_statement_file(raw, upload.name, opening, int(year) if year else None)
        closing = _money(request.POST.get('closing_balance'), 'el saldo final según el banco', required=False)
        if source == 'pdf':
            # El resumen del propio PDF (saldo anterior / saldo actual) manda sobre lo que se escriba a mano.
            header = reconciliation.pdf_header_balances(raw)
            if header['opening'] is not None and (opening is None or opening != header['opening']):
                if opening is not None:
                    warnings.append(f'El saldo inicial que escribiste (${opening}) no es el del PDF: se usó el "saldo anterior" que imprime el banco (${header["opening"]}).')
                opening = header['opening']
            if header['closing'] is not None and (closing is None or closing != header['closing']):
                if closing is not None:
                    warnings.append(f'El saldo final que escribiste (${closing}) no es el del PDF: se usó el "saldo actual" que imprime el banco (${header["closing"]}).')
                closing = header['closing']
        if closing is None:
            last = [r['balance'] for r in rows if r['balance'] is not None]
            if not last:
                raise ValueError('Escribe el saldo final según el banco: el archivo no trae la columna de saldo.')
            closing = last[-1]
            warnings.append(f'El saldo final ({closing}) se tomó de la última fila del archivo.')
        net = sum((r['amount'] for r in rows), Decimal('0.00'))
        if opening is not None:
            expected_closing = (opening + net).quantize(Decimal('0.01'))
            if expected_closing == closing:
                warnings.append(f'Cuadra: saldo inicial ${opening} + movimientos ${net} = saldo final ${closing}.')
            else:
                warnings.append(f'NO CUADRA: saldo inicial ${opening} + movimientos ${net} = ${expected_closing}, pero el saldo final es ${closing} (diferencia ${(expected_closing - closing).quantize(Decimal("0.01"))}). Algún movimiento se leyó mal o falta.')
        with transaction.atomic():
            statement = BankStatement.objects.create(
                bank_account=bank, date_from=min(r['date'] for r in rows), date_to=max(r['date'] for r in rows),
                opening_balance=opening, closing_balance=closing, file_name=upload.name[:200], source=source, created_by=request.user)
            BankStatementLine.objects.bulk_create([
                BankStatementLine(statement=statement, date=r['date'], description=r['description'], reference=r['reference'], amount=r['amount'], balance=r['balance'])
                for r in rows])
            marked = 0
            if opening is not None and reconciliation.book_balance_before(bank, statement.date_from) == opening:
                # El saldo inicial del banco coincide con el libro antes del período: esos asientos ya estaban en el banco.
                marked = reconciliation.mark_opening(statement)
                if marked:
                    warnings.append(f'El saldo inicial coincide con el libro: se dieron por conciliados {marked} asiento(s) anteriores al período.')
            elif opening is not None:
                warnings.append(
                    f'El saldo inicial del banco (${opening}) NO coincide con el libro antes del período '
                    f'(${reconciliation.book_balance_before(bank, statement.date_from)}): hay partidas anteriores sin conciliar. '
                    'Revisa el libro o usa "Marcar anteriores como conciliados".')
            matched = reconciliation.auto_match(statement)
        return {'id': statement.pk, 'lines': len(rows), 'matched': matched, 'warnings': warnings}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Conciliación Bancaria'
        context['banks'] = BankAccount.objects.filter(active=True).order_by('bank_name', 'number')
        return context


class ReconciliationDetailView(AccountingEnabledMixin, GroupPermissionMixin, TemplateView):
    template_name = 'contabilidad/reconciliation/detail.html'
    permission_required = 'view_bankstatement'

    def get_statement(self):
        return BankStatement.objects.select_related('bank_account__account').get(pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        try:
            statement = self.get_statement()
            action = request.POST['action']
            if action == 'summary':
                data = {'statement': statement.toJSON(), 'summary': reconciliation.summary(statement)}
            elif action == 'bank_lines':
                data = [i.toJSON() for i in statement.lines.filter(is_opening=False).select_related('entry_line__entry')]
            elif action == 'book_lines':
                data = []
                for line in reconciliation._unmatched_book_lines(statement.bank_account, statement.date_to):
                    data.append({
                        'id': line.id, 'date': line.entry.date.strftime('%Y-%m-%d'), 'entry': str(line.entry), 'reference': line.entry.reference,
                        'description': line.description or line.entry.description, 'amount': float(reconciliation.book_movement(line)),
                    })
            else:
                _require(request, 'change_bankstatement')
                data = self.change(request, statement, action)
        except Exception as e:
            data = {'error': str(e)}
        return json_response(data)

    def change(self, request, statement, action):
        if action == 'auto_match':
            if statement.status == 'reconciled':
                raise ValueError('La conciliación ya está cerrada.')
            return {'matched': reconciliation.auto_match(statement)}
        if action == 'match':
            reconciliation.manual_match(statement.lines.get(pk=request.POST['line']), JournalEntryLine.objects.select_related('entry').get(pk=request.POST['entry_line']))
            return {}
        if action == 'unmatch':
            return {'voided': reconciliation.unmatch(statement.lines.get(pk=request.POST['line']))}
        if action == 'unmatch_selected':
            ids = [int(i) for i in json.loads(request.POST['lines'])]
            if not ids:
                raise ValueError('No hay movimientos para desconciliar.')
            with transaction.atomic():
                lines = list(statement.lines.filter(pk__in=ids, entry_line__isnull=False, is_opening=False).select_related('entry_line__entry'))
                voided = sum(1 for line in lines if reconciliation.unmatch(line))
            return {'unmatched': len(lines), 'voided': voided}
        if action == 'post':
            counter = Account.objects.get(pk=request.POST['account'], accepts_movement=True, active=True)
            with transaction.atomic():
                reconciliation.post_statement_line(statement.lines.get(pk=request.POST['line']), counter, request.user)
            return {}
        if action == 'post_opening':
            counter = Account.objects.get(pk=request.POST['account'], accepts_movement=True, active=True)
            with transaction.atomic():
                return {'marked': reconciliation.post_opening(statement, counter, request.user)}
        if action == 'post_selected':
            ids = [int(i) for i in json.loads(request.POST['lines'])]
            if not ids:
                raise ValueError('No hay movimientos para registrar.')
            counter = Account.objects.get(pk=request.POST['account'], accepts_movement=True, active=True)
            with transaction.atomic():
                lines = list(statement.lines.filter(pk__in=ids, entry_line__isnull=True, is_opening=False).order_by('date', 'id'))
                for line in lines:
                    reconciliation.post_statement_line(line, counter, request.user)
            return {'posted': len(lines)}
        if action == 'post_all':
            accounts = {k: Account.objects.get(pk=request.POST[k], accepts_movement=True, active=True) for k in ('income_account', 'expense_account', 'fee_account')}
            with transaction.atomic():
                return {'posted': reconciliation.post_pending(statement, accounts['income_account'], accounts['expense_account'], accounts['fee_account'], request.user)}
        if action == 'mark_opening':
            return {'marked': reconciliation.mark_opening(statement)}
        if action == 'clear_opening':
            return {'cleared': reconciliation.clear_opening(statement)}
        if action == 'flip_sign':
            if statement.status == 'reconciled':
                raise ValueError('La conciliación ya está cerrada.')
            line = statement.lines.get(pk=request.POST['line'])
            if line.entry_line_id:
                raise ValueError('Primero desconcilia el movimiento.')
            line.amount = -line.amount
            line.save(update_fields=['amount'])
            return {}
        if action == 'delete_line':
            if statement.status == 'reconciled':
                raise ValueError('La conciliación ya está cerrada.')
            line = statement.lines.get(pk=request.POST['line'])
            if line.entry_line_id:
                raise ValueError('Primero desconcilia el movimiento.')
            line.delete()
            return {}
        if action == 'set_closing':
            if statement.status == 'reconciled':
                raise ValueError('La conciliación ya está cerrada.')
            statement.closing_balance = _money(request.POST.get('closing_balance'), 'el saldo final según el banco')
            statement.save(update_fields=['closing_balance'])
            return {}
        if action == 'reconcile':
            result = reconciliation.summary(statement)
            if not result['balanced']:
                raise ValueError(f'Todavía hay una diferencia de ${result["difference"]:.2f}. Concilia o registra los movimientos pendientes hasta que sea 0.00.')
            statement.status, statement.reconciled_at, statement.reconciled_by = 'reconciled', timezone.now(), request.user
            statement.save(update_fields=['status', 'reconciled_at', 'reconciled_by'])
            return {}
        if action == 'reopen':
            statement.status, statement.reconciled_at, statement.reconciled_by = 'open', None, None
            statement.save(update_fields=['status', 'reconciled_at', 'reconciled_by'])
            return {}
        raise ValueError('No ha seleccionado ninguna opción')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        statement = self.get_statement()
        context['title'] = 'Conciliación bancaria'
        context['statement'] = statement
        context['accounts'] = Account.objects.filter(accepts_movement=True, active=True).exclude(pk=statement.bank_account.account_id).order_by('code')
        context['default_expense'] = Account.objects.filter(accepts_movement=True, code__startswith='6.1.03').first()
        context['default_income'] = Account.objects.filter(accepts_movement=True, code__startswith='4.2.01').first()
        context['default_capital'] = Account.objects.filter(accepts_movement=True, code='3.1.01').first()
        context['default_general'] = Account.objects.filter(accepts_movement=True, code='6.1.02').first()
        return context

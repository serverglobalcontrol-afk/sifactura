"""Estados financieros a partir del libro contable (asientos CONTABILIZADOS):

  * Estado de situación financiera (balance general) a una fecha.
  * Estado de resultados de un período.

Cada cuenta suma los saldos de sus hijas (el plan es jerárquico). El resultado
del ejercicio no se guarda en ninguna cuenta (no hay asiento de cierre): se
calcula aquí y se muestra como una línea aparte dentro del patrimonio, así el
balance siempre cuadra sin tocar los asientos.

La parte que arma las filas (`build_rows`) no usa la base de datos para poder
probarla sola.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum

ZERO = Decimal('0.00')
DEBIT_NATURE = ('activo', 'costo', 'gasto')


def signed(account_type, debit, credit):
    """Saldo según la naturaleza: deudora (activo, costo, gasto) o acreedora."""
    debit, credit = Decimal(debit or 0), Decimal(credit or 0)
    return (debit - credit) if account_type in DEBIT_NATURE else (credit - debit)


def ledger_balances(date_from=None, date_to=None):
    """{id de cuenta: saldo con signo de su naturaleza} de los asientos contabilizados."""
    from core.contabilidad.models import Account, JournalEntryLine
    lines = JournalEntryLine.objects.filter(entry__status='posted')
    if date_from:
        lines = lines.filter(entry__date__gte=date_from)
    if date_to:
        lines = lines.filter(entry__date__lte=date_to)
    types = dict(Account.objects.values_list('id', 'account_type'))
    result = {}
    for row in lines.values('account').annotate(d=Sum('debit'), c=Sum('credit')):
        result[row['account']] = signed(types.get(row['account']), row['d'], row['c'])
    return result


def accounts_as_dicts():
    from core.contabilidad.models import Account
    return [
        {'id': a.id, 'code': a.code, 'name': a.name, 'parent_id': a.parent_id, 'type': a.account_type}
        for a in Account.objects.order_by('code')
    ]


def _totals(accounts, balances):
    """Total de cada cuenta = su saldo propio + el de todas sus descendientes."""
    totals = {a['id']: Decimal(balances.get(a['id'], ZERO)) for a in accounts}
    by_id = {a['id']: a for a in accounts}
    for a in accounts:
        parent = a['parent_id']
        seen = set()
        while parent is not None and parent in by_id and parent not in seen:
            seen.add(parent)
            totals[parent] += Decimal(balances.get(a['id'], ZERO))
            parent = by_id[parent]['parent_id']
    return totals


def _depth(account, by_id):
    depth, parent, seen = 0, account['parent_id'], set()
    while parent is not None and parent in by_id and parent not in seen:
        seen.add(parent)
        depth += 1
        parent = by_id[parent]['parent_id']
    return depth


def build_rows(accounts, balances, types):
    """Filas (jerarquía) de las cuentas de los `types` indicados con total distinto de cero,
    más el total de esos tipos. Devuelve (filas, total_de_los_tipos)."""
    by_id = {a['id']: a for a in accounts}
    totals = _totals(accounts, balances)
    rows = []
    for a in accounts:
        if a['type'] not in types:
            continue
        total = totals[a['id']]
        if total == 0:
            continue
        rows.append({
            'code': a['code'], 'name': a['name'], 'level': _depth(a, by_id), 'amount': float(total),
            'kind': 'account', 'id': a['id'],
        })
    roots = [a for a in accounts if a['type'] in types and (a['parent_id'] is None or by_id.get(a['parent_id'], {}).get('type') not in types)]
    grand = sum((totals[a['id']] for a in roots), ZERO)
    for row in rows:
        # Una cuenta con hijas se resalta como grupo.
        row['kind'] = 'group' if any(c['parent_id'] == row['id'] and totals[c['id']] != 0 for c in accounts) else 'account'
        del row['id']
    return rows, grand


def _line(name, amount, kind='total', code='', level=0):
    return {'code': code, 'name': name, 'level': level, 'amount': float(amount), 'kind': kind}


def balance_sheet(accounts, balances_to_date, balances_prior_years, balances_year_to_date):
    """Estado de situación financiera.

    balances_to_date        : saldos acumulados hasta la fecha del balance.
    balances_prior_years    : resultado (ingresos - costos - gastos) de años ANTERIORES, ya calculado (Decimal).
    balances_year_to_date   : resultado del año en curso hasta la fecha, ya calculado (Decimal).
    """
    rows = []
    assets, total_assets = build_rows(accounts, balances_to_date, ('activo',))
    liabilities, total_liabilities = build_rows(accounts, balances_to_date, ('pasivo',))
    equity, total_equity = build_rows(accounts, balances_to_date, ('patrimonio',))
    rows += assets
    rows.append(_line('TOTAL ACTIVO', total_assets))
    rows += liabilities
    rows.append(_line('TOTAL PASIVO', total_liabilities))
    rows += equity
    prior, current = Decimal(balances_prior_years), Decimal(balances_year_to_date)
    if prior != 0:
        rows.append(_line('Resultado de ejercicios anteriores (calculado)', prior, 'account', level=1))
    if current != 0:
        rows.append(_line('Resultado del ejercicio (calculado)', current, 'account', level=1))
    total_equity_all = total_equity + prior + current
    rows.append(_line('TOTAL PATRIMONIO', total_equity_all))
    rows.append(_line('TOTAL PASIVO + PATRIMONIO', total_liabilities + total_equity_all))
    difference = total_assets - (total_liabilities + total_equity_all)
    rows.append(_line('DIFERENCIA (Activo - Pasivo - Patrimonio): debe ser 0.00', difference, 'check'))
    return rows


def income_statement(accounts, balances_in_period):
    """Estado de resultados del período."""
    income, total_income = build_rows(accounts, balances_in_period, ('ingreso',))
    costs, total_costs = build_rows(accounts, balances_in_period, ('costo',))
    expenses, total_expenses = build_rows(accounts, balances_in_period, ('gasto',))
    gross = total_income - total_costs
    net = gross - total_expenses
    rows = []
    rows += income
    rows.append(_line('TOTAL INGRESOS', total_income))
    rows += costs
    rows.append(_line('TOTAL COSTOS', total_costs))
    rows.append(_line('UTILIDAD BRUTA', gross))
    rows += expenses
    rows.append(_line('TOTAL GASTOS', total_expenses))
    rows.append(_line('UTILIDAD (PÉRDIDA) ANTES DE PARTICIPACIÓN E IMPUESTOS', net))
    return rows


# ---------------------------------------------------------------- con base de datos
def get_balance_sheet(as_of):
    accounts = accounts_as_dicts()
    to_date = ledger_balances(date_to=as_of)
    year_start = date(as_of.year, 1, 1)
    prior = ledger_balances(date_to=year_start - timedelta(days=1))
    current = ledger_balances(date_from=year_start, date_to=as_of)
    by_type = {a['id']: a['type'] for a in accounts}

    def result(balances):
        value = ZERO
        for account_id, amount in balances.items():
            account_type = by_type.get(account_id)
            if account_type == 'ingreso':
                value += amount
            elif account_type in ('costo', 'gasto'):
                value -= amount
        return value

    # Las cuentas de resultado NO entran al balance: solo activo, pasivo y patrimonio.
    return balance_sheet(accounts, to_date, result(prior), result(current))


def get_income_statement(date_from, date_to):
    return income_statement(accounts_as_dicts(), ledger_balances(date_from=date_from, date_to=date_to))


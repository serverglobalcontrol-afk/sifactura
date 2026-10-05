"""Motor de asientos automáticos.

Cada operación del sistema (venta, cobro, compra...) es un *origen* (`kind`
+ `pk`). Para cada origen hay un *builder* que, a partir del estado ACTUAL del
documento en la base de datos, devuelve las líneas del asiento (o None si el
documento ya no debe contabilizarse). `sync_source` compara ese resultado con
el asiento existente y lo crea, lo regenera, lo anula o lo deja igual: es
**idempotente**, así que llamarlo dos veces (o desde un barrido masivo) nunca
duplica nada.

Reglas de negocio importantes:
- Los tickets de venta (comprobante 08) y las liquidaciones de compra (03) NO
  se contabilizan como ventas.
- Una venta anulada sin nota de crédito deja de existir contablemente; si
  tiene nota de crédito, la venta se mantiene y la nota la reversa.
- Los abonos generados por una retención (`retention_id`) no son dinero
  recibido: no se contabilizan como cobro (la retención tiene su propio
  asiento).
- Se lee siempre de la base de datos (no de la instancia en memoria): los
  totales de Sale/CreditNote quedan como float en memoria.
"""
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from crum import get_current_user
from django.db import transaction
from django.utils import timezone

from core.contabilidad.models import (
    Account, AccountMapping, AccountingConfig, AccountingPeriod, BankAccount, BankAlias,
    JournalEntry, JournalEntryLine, TypeAccountMapping,
)
from core.pos.choices import INVOICE_STATUS, VOUCHER_TYPE

logger = logging.getLogger('invoicepro')

ZERO = Decimal('0.00')
CENT = Decimal('0.01')
# Diferencia máxima (por redondeo de centavos entre los totales del documento
# y la suma de sus partes) que se absorbe en la cuenta "Ajuste por redondeo".
ROUNDING_TOLERANCE = Decimal('0.02')

CASH_TYPES = ('efectivo', 'cash')
BANK_TYPES = ('transferencia', 'transfer', 'deposit', 'check')


class MissingMapping(Exception):
    pass


class UnbalancedEntry(Exception):
    pass


class PeriodClosed(Exception):
    pass


def D(value):
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def local_date(value):
    """Fecha local (America/Guayaquil) de un date o datetime."""
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.date()
    return value


def _norm(text):
    text = unicodedata.normalize('NFD', (text or '').strip().lower())
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


@dataclass
class Line:
    account: Account
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    description: str = ''
    bank_account: object = None
    third_party: str = ''
    third_party_id: str = ''


@dataclass
class Built:
    date: date
    description: str
    lines: list = field(default_factory=list)


def dr(account, amount, **kw):
    amount = D(amount)
    return Line(account=account, debit=amount, **kw) if amount > 0 else None


def cr(account, amount, **kw):
    amount = D(amount)
    return Line(account=account, credit=amount, **kw) if amount > 0 else None


class Ctx:
    """Cuentas configuradas de la empresa, cargadas una sola vez por
    sincronización."""

    def __init__(self):
        self.roles = {m.role: m.account for m in AccountMapping.objects.select_related('account')}
        self._banks = None
        self._aliases = None
        self._types = None

    def account(self, role):
        try:
            return self.roles[role]
        except KeyError:
            raise MissingMapping(f'Falta configurar la cuenta contable del rol "{role}" (Contabilidad > Configuración).')

    def _load_banks(self):
        if self._banks is None:
            self._banks = list(BankAccount.objects.filter(active=True).select_related('account'))
            self._aliases = {_norm(a.text): a.bank_account for a in BankAlias.objects.select_related('bank_account__account')}

    def bank(self, text=None):
        """(cuenta contable, cuenta bancaria o None) para el texto de banco
        que escribió el usuario en el POS. Orden: alias exacto, banco con
        nombre parecido, banco por defecto."""
        self._load_banks()
        key = _norm(text)
        if key:
            bank = self._aliases.get(key)
            if bank is None and len(key) >= 3:
                for candidate in self._banks:
                    name = _norm(candidate.bank_name)
                    if key in name or name in key:
                        bank = candidate
                        break
            if bank is not None:
                return bank.account, bank
        return self.account('banco_defecto'), None

    def type_account(self, kind, type_id, default_role):
        if self._types is None:
            self._types = {(m.kind, m.type_id): m.account for m in TypeAccountMapping.objects.select_related('account')}
        return self._types.get((kind, type_id)) or self.account(default_role)

    def money(self, payment_type, bank_text=None):
        """(cuenta, cuenta bancaria) donde entra o sale el dinero según la
        forma de pago."""
        if payment_type in CASH_TYPES:
            return self.account('caja'), None
        if payment_type == 'tarjeta_credito':
            return self.account('tarjetas'), None
        return self.bank(bank_text)


def _lines(*items):
    return [i for i in items if i is not None]


def finalize(ctx, lines):
    """Valida que el asiento cuadre. Una diferencia de hasta 2 centavos (por
    redondeo) se asienta en 'Ajuste por redondeo'; mayor que eso es un error."""
    total_debit = sum((l.debit for l in lines), ZERO)
    total_credit = sum((l.credit for l in lines), ZERO)
    diff = total_debit - total_credit
    if diff == 0:
        return lines
    if abs(diff) > ROUNDING_TOLERANCE:
        raise UnbalancedEntry(f'El asiento no cuadra: Debe {total_debit} / Haber {total_credit}.')
    adjust = ctx.account('redondeo')
    lines = list(lines)
    lines.append(Line(account=adjust, credit=diff, description='Ajuste por redondeo') if diff > 0 else Line(account=adjust, debit=-diff, description='Ajuste por redondeo'))
    return lines


# --------------------------------------------------------------------------
# Builders: reciben el objeto recién leído de la BD y devuelven Built o None.
# --------------------------------------------------------------------------

def _is_invoice(sale):
    return sale.receipt.voucher_type == VOUCHER_TYPE[0][0]


def _sale_is_void(sale):
    """Venta anulada sin nota de crédito: nunca fue una venta válida."""
    return sale.status == INVOICE_STATUS[3][0] and not sale.creditnote_set.exists()


def _client_of(sale):
    return sale.client.user.names or '', sale.client.dni or ''


def _sale_money_line(ctx, sale, amount, side, **kw):
    """Línea del lado 'cobro' de una venta: Clientes si fue a crédito; si no,
    Caja/Banco/Tarjetas según cómo pagó."""
    make = dr if side == 'debit' else cr
    if sale.payment_type == 'credito':
        return make(ctx.account('clientes'), amount, **kw)
    account, bank = ctx.money(sale.payment_type, sale.transfer_bank)
    return make(account, amount, bank_account=bank, **kw)


def build_sale(ctx, sale):
    if not _is_invoice(sale) or _sale_is_void(sale):
        return None
    name, dni = _client_of(sale)
    tp = {'third_party': name, 'third_party_id': dni}
    total = D(sale.total)
    if total <= 0:
        return None
    cost = ZERO
    for detail in sale.saledetail_set.select_related('product'):
        if detail.product.inventoried:
            cost += D(detail.cant) * D(detail.product.price)
    lines = _lines(
        _sale_money_line(ctx, sale, total, 'debit', **tp),
        cr(ctx.account('ventas_gravadas'), sale.subtotal_12, **tp),
        cr(ctx.account('ventas_0'), sale.subtotal_0, **tp),
        cr(ctx.account('iva_ventas'), sale.total_iva, **tp),
        dr(ctx.account('costo_ventas'), cost, description='Costo de ventas'),
        cr(ctx.account('inventario'), cost, description='Salida de inventario'),
    )
    return Built(sale.date_joined, f'Venta {sale.voucher_number_full} - {name}', lines)


def build_credit_note(ctx, nc):
    sale = nc.sale
    if nc.status == INVOICE_STATUS[3][0] or not _is_invoice(sale):
        return None
    name, dni = _client_of(sale)
    tp = {'third_party': name, 'third_party_id': dni}
    total = D(nc.total)
    if total <= 0:
        return None
    if sale.payment_type == 'credito':
        refund = cr(ctx.account('clientes'), total, **tp)
    else:
        account, bank = ctx.money(nc.refund_method, sale.transfer_bank)
        refund = cr(account, total, bank_account=bank, **tp)
    cost = ZERO
    for detail in nc.creditnotedetail_set.select_related('product'):
        if detail.product is not None and detail.product.inventoried:
            cost += D(detail.cant) * D(detail.product.price)
    lines = _lines(
        dr(ctx.account('devoluciones'), D(nc.subtotal_12) + D(nc.subtotal_0), **tp),
        dr(ctx.account('iva_ventas'), nc.total_iva, **tp),
        refund,
        dr(ctx.account('inventario'), cost, description='Reingreso a inventario'),
        cr(ctx.account('costo_ventas'), cost, description='Reverso de costo de ventas'),
    )
    return Built(local_date(nc.date_joined), f'Nota de crédito {nc.voucher_number_full} (venta {sale.voucher_number_full}) - {name}', lines)


def build_collection(ctx, pay):
    if pay.retention_id:
        return None
    sale = pay.ctas_collect.sale
    if not _is_invoice(sale) or _sale_is_void(sale):
        return None
    name, dni = _client_of(sale)
    account, bank = ctx.money(pay.payment_type, pay.bank_entity)
    amount = D(pay.valor)
    lines = _lines(
        dr(account, amount, bank_account=bank, third_party=name, third_party_id=dni),
        cr(ctx.account('clientes'), amount, third_party=name, third_party_id=dni),
    )
    return Built(local_date(pay.date_joined), f'Cobro de {sale.voucher_number_full} - {name}', lines)


def build_retention(ctx, ret):
    sale = ret.sale
    if not _is_invoice(sale) or _sale_is_void(sale):
        return None
    name, dni = _client_of(sale)
    tp = {'third_party': name, 'third_party_id': dni}
    total = D(ret.iva_retained) + D(ret.income_tax_retained)
    lines = _lines(
        dr(ctx.account('ret_iva'), ret.iva_retained, **tp),
        dr(ctx.account('ret_renta'), ret.income_tax_retained, **tp),
        _sale_money_line(ctx, sale, total, 'credit', **tp),
    )
    return Built(ret.issue_date, f'Retención {ret.document_number} sobre {sale.voucher_number_full} - {name}', lines)


def build_purchase(ctx, purchase):
    provider = purchase.provider
    tp = {'third_party': provider.name, 'third_party_id': provider.ruc}
    inventory = ZERO
    other = ZERO
    for detail in purchase.purchasedetail_set.select_related('product'):
        if detail.product.inventoried:
            inventory += D(detail.subtotal)
        else:
            other += D(detail.subtotal)
    total = inventory + other
    if total <= 0:
        return None
    paid = ctx.account('caja') if purchase.payment_type in CASH_TYPES else ctx.account('proveedores')
    lines = _lines(
        dr(ctx.account('inventario'), inventory, **tp),
        dr(ctx.account('compras_no_inv'), other, **tp),
        cr(paid, total, **tp),
    )
    return Built(local_date(purchase.date_joined), f'Compra {purchase.number} - {provider.name}', lines)


def build_supplier_payment(ctx, pay):
    provider = pay.debts_pay.purchase.provider
    tp = {'third_party': provider.name, 'third_party_id': provider.ruc}
    account, bank = ctx.money(pay.payment_type, pay.bank_entity)
    amount = D(pay.valor)
    lines = _lines(
        dr(ctx.account('proveedores'), amount, **tp),
        cr(account, amount, bank_account=bank, **tp),
    )
    return Built(local_date(pay.date_joined), f'Pago a {provider.name} (compra {pay.debts_pay.purchase.number})', lines)


def build_expense(ctx, expense):
    amount = D(expense.valor)
    if amount <= 0:
        return None
    account = ctx.type_account('expense', expense.type_expense_id, 'gasto_defecto')
    detail = f' - {expense.description}' if expense.description else ''
    lines = _lines(
        dr(account, amount, description=expense.description or ''),
        # Los gastos no tienen forma de pago propia: igual que el cierre de
        # caja, se asumen pagados en efectivo.
        cr(ctx.account('caja'), amount),
    )
    return Built(local_date(expense.date_joined), f'Gasto: {expense.type_expense.name}{detail}', lines)


def build_income(ctx, income):
    amount = D(income.valor)
    if amount <= 0:
        return None
    account, bank = ctx.money(income.payment_type)
    credit_account = ctx.type_account('income', income.type_income_id, 'ingreso_defecto')
    detail = f' - {income.description}' if income.description else ''
    lines = _lines(
        dr(account, amount, bank_account=bank),
        cr(credit_account, amount, description=income.description or ''),
    )
    return Built(local_date(income.date_joined), f'Ingreso: {income.type_income.name}{detail}', lines)


def build_cash_closing(ctx, register):
    difference = D(register.difference)
    if register.status != 'closed' or difference == 0:
        return None
    when = local_date(register.closing_datetime) if register.closing_datetime else register.date_joined
    caja = ctx.account('caja')
    if difference > 0:
        lines = _lines(dr(caja, difference), cr(ctx.account('sobrante_caja'), difference))
        label = 'Sobrante'
    else:
        lines = _lines(dr(ctx.account('faltante_caja'), -difference), cr(caja, -difference))
        label = 'Faltante'
    return Built(when, f'{label} en cierre de caja de {register.user.username} ({register.date_joined})', lines)


def build_payroll(ctx, salary):
    from django.db.models import Sum
    totals = salary.salarydetail_set.aggregate(income=Sum('income'), expenses=Sum('expenses'), total=Sum('total_amount'))
    income, expenses, total = D(totals['income']), D(totals['expenses']), D(totals['total'])
    if income <= 0:
        return None
    lines = _lines(
        dr(ctx.account('sueldos_gasto'), income),
        cr(ctx.account('sueldos_pagar'), total),
        cr(ctx.account('descuentos_nomina'), expenses),
    )
    return Built(salary.payment_date, f'Nómina {salary.year}-{int(salary.month):02d}', lines)


# --------------------------------------------------------------------------
# Registro de orígenes: cómo cargar cada uno, cómo construirlo y cómo listar
# los de un rango de fechas (para el barrido "Contabilizar pendientes").
# --------------------------------------------------------------------------

def _get(model, pk, *related):
    try:
        qs = model.objects.select_related(*related) if related else model.objects
        return qs.get(pk=pk)
    except model.DoesNotExist:
        return None


def _sources():
    from core.pos.models import (
        CashRegister, CreditNote, Expenses, Income, PaymentsCtaCollect, PaymentsDebtsPay, Purchase, Retention, Sale,
    )
    from core.rrhh.models import Salary
    return {
        'sale': dict(
            load=lambda pk: _get(Sale, pk, 'receipt', 'client__user'),
            build=build_sale,
            range=lambda a, b: Sale.objects.filter(date_joined__range=(a, b)),
        ),
        'credit_note': dict(
            load=lambda pk: _get(CreditNote, pk, 'sale__receipt', 'sale__client__user'),
            build=build_credit_note,
            range=lambda a, b: CreditNote.objects.filter(date_joined__date__range=(a, b)),
        ),
        'collection': dict(
            load=lambda pk: _get(PaymentsCtaCollect, pk, 'ctas_collect__sale__receipt', 'ctas_collect__sale__client__user'),
            build=build_collection,
            range=lambda a, b: PaymentsCtaCollect.objects.filter(date_joined__date__range=(a, b), retention__isnull=True),
        ),
        'retention': dict(
            load=lambda pk: _get(Retention, pk, 'sale__receipt', 'sale__client__user'),
            build=build_retention,
            range=lambda a, b: Retention.objects.filter(issue_date__range=(a, b)),
        ),
        'purchase': dict(
            load=lambda pk: _get(Purchase, pk, 'provider'),
            build=build_purchase,
            range=lambda a, b: Purchase.objects.filter(date_joined__date__range=(a, b)),
        ),
        'supplier_payment': dict(
            load=lambda pk: _get(PaymentsDebtsPay, pk, 'debts_pay__purchase__provider'),
            build=build_supplier_payment,
            range=lambda a, b: PaymentsDebtsPay.objects.filter(date_joined__date__range=(a, b)),
        ),
        'expense': dict(
            load=lambda pk: _get(Expenses, pk, 'type_expense'),
            build=build_expense,
            range=lambda a, b: Expenses.objects.filter(date_joined__date__range=(a, b)),
        ),
        'income': dict(
            load=lambda pk: _get(Income, pk, 'type_income'),
            build=build_income,
            range=lambda a, b: Income.objects.filter(date_joined__date__range=(a, b)),
        ),
        'cash_closing': dict(
            load=lambda pk: _get(CashRegister, pk, 'user'),
            build=build_cash_closing,
            range=lambda a, b: CashRegister.objects.filter(status='closed', closing_datetime__date__range=(a, b)),
        ),
        'payroll': dict(
            load=lambda pk: _get(Salary, pk),
            build=build_payroll,
            range=lambda a, b: Salary.objects.filter(payment_date__range=(a, b)),
        ),
    }


# Los cobros (abonos) cuyo origen desaparece NO se anulan en el barrido: si una
# anulación borra la cuenta por cobrar en cascada, el dinero ya se recibió de
# verdad y el asiento del cobro sigue siendo correcto. Un abono que el usuario
# elimina a propósito sí se anula, porque la vista lo contabiliza al borrarlo.
ORPHANS_KEPT = ('collection',)

SOURCE_KINDS = ('sale', 'credit_note', 'collection', 'retention', 'purchase', 'supplier_payment', 'expense', 'income', 'cash_closing', 'payroll')


def _signature(built_lines, entry_date, description):
    return (
        entry_date, description,
        sorted(((l.account.pk, l.debit, l.credit, getattr(l.bank_account, 'pk', None), l.third_party, l.description) for l in built_lines), key=str),
    )


def _existing_signature(entry):
    return (
        entry.date, entry.description,
        sorted(((l.account_id, l.debit, l.credit, l.bank_account_id, l.third_party, l.description) for l in entry.lines.all()), key=str),
    )


def _current_user():
    user = get_current_user()
    return user if user is not None and getattr(user, 'is_authenticated', False) else None


def _void(existing, reason):
    if existing is None or existing.status == 'voided':
        return 'skipped'
    if AccountingPeriod.is_closed(existing.date):
        return 'blocked'
    existing.status = 'voided'
    existing.void_reason = reason
    existing.updated_at = timezone.now()
    existing.save(update_fields=['status', 'void_reason', 'updated_at'])
    return 'voided'


def sync_source(kind, pk):
    """Crea, regenera, anula o deja igual el asiento del origen `kind`:`pk`.
    Devuelve: created | updated | voided | unchanged | skipped | blocked."""
    spec = _sources()[kind]
    config = AccountingConfig.get()
    if config is None:
        return 'skipped'
    key = f'{kind}:{pk}'
    existing = JournalEntry.objects.select_for_update().filter(source_key=key).first()
    obj = spec['load'](pk)
    ctx = Ctx()
    built = spec['build'](ctx, obj) if obj is not None else None
    if built is None:
        return _void(existing, 'El documento de origen ya no aplica (anulado, eliminado o excluido)')
    if built.date < config.start_date:
        return 'skipped'
    if AccountingPeriod.is_closed(built.date) or (existing and AccountingPeriod.is_closed(existing.date)):
        return 'blocked'
    lines = finalize(ctx, built.lines)
    if existing and existing.status == 'posted' and _signature(lines, built.date, built.description) == _existing_signature(existing):
        return 'unchanged'
    with transaction.atomic():
        now = timezone.now()
        if existing:
            existing.lines.all().delete()
            existing.date = built.date
            existing.description = built.description[:300]
            existing.status = 'posted'
            existing.void_reason = ''
            existing.updated_at = now
            existing.save()
            entry, result = existing, 'updated'
        else:
            entry = JournalEntry.objects.create(
                number=JournalEntry.next_number(), date=built.date, description=built.description[:300],
                source_type=kind, source_id=pk, source_key=key, created_by=_current_user(),
            )
            result = 'created'
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(
                entry=entry, account=l.account, debit=l.debit, credit=l.credit, description=(l.description or '')[:300],
                bank_account=l.bank_account, third_party=(l.third_party or '')[:200], third_party_id=(l.third_party_id or '')[:20],
            ) for l in lines
        ])
        entry.recalculate_totals()
    return result


def safe_sync(kind, pk):
    """Como sync_source, pero jamás propaga una excepción (savepoint propio:
    si algo falla a medias, se deshace solo el asiento, no la venta)."""
    try:
        with transaction.atomic():
            return sync_source(kind, pk)
    except Exception:
        logger.exception('Contabilidad: fallo al contabilizar %s:%s', kind, pk)
        return 'error'


def post_pending(start, end):
    """Barrido: contabiliza todo lo que falte entre `start` y `end` (ambos
    inclusive) y anula los asientos cuyo origen ya no existe. Devuelve un
    resumen {estado: cantidad} y la lista de errores."""
    summary = {'created': 0, 'updated': 0, 'voided': 0, 'unchanged': 0, 'skipped': 0, 'blocked': 0}
    errors = []
    sources = _sources()
    for kind in SOURCE_KINDS:
        pks = list(sources[kind]['range'](start, end).values_list('pk', flat=True))
        orphans = [] if kind in ORPHANS_KEPT else JournalEntry.objects.filter(
            source_type=kind, status='posted', date__range=(start, end),
        ).exclude(source_id__in=pks).values_list('source_id', flat=True)
        for pk in pks + list(orphans):
            try:
                with transaction.atomic():
                    result = sync_source(kind, pk)
                summary[result] += 1
            except Exception as e:
                logger.exception('Contabilidad: fallo al contabilizar %s:%s', kind, pk)
                errors.append(f'{kind}:{pk} - {e}')
    return summary, errors


# --------------------------------------------------------------------------
# Asientos manuales y movimientos bancarios
# --------------------------------------------------------------------------

def create_manual_entry(entry_date, description, lines, source_type='manual', user=None):
    """Crea un asiento manual. `lines` es una lista de Line; debe cuadrar
    exactamente (sin tolerancia de redondeo)."""
    lines = [l for l in lines if l.debit > 0 or l.credit > 0]
    if len(lines) < 2:
        raise UnbalancedEntry('El asiento necesita al menos dos líneas con valor.')
    total_debit = sum((l.debit for l in lines), ZERO)
    total_credit = sum((l.credit for l in lines), ZERO)
    if total_debit != total_credit:
        raise UnbalancedEntry(f'El asiento no cuadra: Debe {total_debit} / Haber {total_credit}.')
    if AccountingPeriod.is_closed(entry_date):
        raise PeriodClosed(f'El período {entry_date.year}-{entry_date.month:02d} está cerrado.')
    with transaction.atomic():
        entry = JournalEntry.objects.create(
            number=JournalEntry.next_number(), date=entry_date, description=description[:300],
            source_type=source_type, created_by=user or _current_user(),
        )
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(
                entry=entry, account=l.account, debit=l.debit, credit=l.credit, description=(l.description or '')[:300],
                bank_account=l.bank_account, third_party=(l.third_party or '')[:200], third_party_id=(l.third_party_id or '')[:20],
            ) for l in lines
        ])
        entry.recalculate_totals()
    return entry


def void_manual_entry(entry, reason):
    if entry.source_key:
        raise ValueError('Este asiento lo genera el sistema desde un documento; se anula anulando o corrigiendo el documento de origen.')
    if entry.status == 'voided':
        raise ValueError('El asiento ya está anulado.')
    if AccountingPeriod.is_closed(entry.date):
        raise PeriodClosed(f'El período {entry.date.year}-{entry.date.month:02d} está cerrado.')
    entry.status = 'voided'
    entry.void_reason = reason[:200]
    entry.updated_at = timezone.now()
    entry.save(update_fields=['status', 'void_reason', 'updated_at'])


def create_bank_move(kind, entry_date, amount, bank_account, other_bank_account=None, description='', user=None):
    """Movimiento bancario como asiento: depósito de caja a banco, retiro de
    banco a caja, transferencia entre cuentas bancarias o comisión bancaria."""
    ctx = Ctx()
    amount = D(amount)
    if amount <= 0:
        raise UnbalancedEntry('El valor debe ser mayor a cero.')
    if kind == 'deposit':
        lines = [dr(bank_account.account, amount, bank_account=bank_account), cr(ctx.account('caja'), amount)]
        label = f'Depósito de caja a {bank_account}'
    elif kind == 'withdrawal':
        lines = [dr(ctx.account('caja'), amount), cr(bank_account.account, amount, bank_account=bank_account)]
        label = f'Retiro de {bank_account} a caja'
    elif kind == 'transfer':
        if other_bank_account is None or other_bank_account.pk == bank_account.pk:
            raise UnbalancedEntry('Elige una cuenta de destino distinta a la de origen.')
        lines = [
            dr(other_bank_account.account, amount, bank_account=other_bank_account),
            cr(bank_account.account, amount, bank_account=bank_account),
        ]
        label = f'Transferencia de {bank_account} a {other_bank_account}'
    elif kind == 'fee':
        lines = [dr(ctx.account('gasto_bancario'), amount), cr(bank_account.account, amount, bank_account=bank_account)]
        label = f'Comisión bancaria {bank_account}'
    else:
        raise ValueError('Tipo de movimiento bancario no válido.')
    return create_manual_entry(entry_date, f'{label}. {description}'.strip(), lines, source_type='bank_move', user=user)

from django.db import transaction

from core.contabilidad.chart import BANKS_PARENT_CODE
from core.contabilidad.models import Account, BankAccount


def next_child_code(parent):
    """Siguiente código libre bajo `parent` (p. ej. 1.1.01.02.03 -> .04)."""
    last = 0
    for code in Account.objects.filter(parent=parent).values_list('code', flat=True):
        try:
            last = max(last, int(code.rsplit('.', 1)[1]))
        except (IndexError, ValueError):
            continue
    return f'{parent.code}.{last + 1:02d}'


def create_bank_account(bank_name, number, account_type='ahorros', holder=''):
    """Crea la cuenta bancaria y su cuenta contable hija de 'Bancos'."""
    parent = Account.objects.get(code=BANKS_PARENT_CODE)
    with transaction.atomic():
        account = Account.objects.create(
            code=next_child_code(parent),
            name=f'{bank_name} {account_type} {number}'[:150],
            parent=parent,
            account_type=parent.account_type,
            accepts_movement=True,
            is_system=False,
        )
        return BankAccount.objects.create(
            bank_name=bank_name, number=number, account_type=account_type, holder=holder, account=account,
        )

from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model, schema_context

from core.pos.models import CtasCollect, DebtsPay

CENT = Decimal('0.01')


def expected(debt, payments):
    """Saldo y estado que le corresponden a una cuenta: deuda - todos los abonos (incluidas las
    retenciones aplicadas), en centavos exactos."""
    paid = sum((Decimal(v) for v in payments), Decimal('0'))
    balance = (Decimal(debt) - paid).quantize(CENT, rounding=ROUND_HALF_UP)
    return balance, balance > 0


class Command(BaseCommand):
    help = (
        'Revisa las Cuentas por Cobrar y por Pagar de cada empresa: deuda - abonos (con retenciones) debe ser el saldo, y la '
        'cuenta solo "Adeuda" si el saldo es mayor a 0.00. Por defecto solo MUESTRA lo que no cuadra; con --apply lo corrige. '
        'Corrige el caso de cuentas con saldo $0.00 que seguían como "Adeuda" por un error de redondeo.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Corregir (sin esta opción solo se muestra).')
        parser.add_argument('--schema', help='Limitar a un solo schema (por defecto todos).')

    def handle(self, *args, **options):
        apply = options['apply']
        total = 0
        for tenant in get_tenant_model().objects.exclude(schema_name='public').order_by('schema_name'):
            if options['schema'] and tenant.schema_name != options['schema']:
                continue
            with schema_context(tenant.schema_name):
                found = self.check_receivables(apply) + self.check_payables(apply)
            total += found
            self.stdout.write(f'{tenant.schema_name}: {found} cuenta(s) por corregir' if found else f'{tenant.schema_name}: todo cuadra')
        if total and not apply:
            self.stdout.write(self.style.WARNING(f'\nTotal: {total}. Para corregirlas: manage.py repair_debt_states --apply'))
        elif total:
            self.stdout.write(self.style.SUCCESS(f'\nCorregidas: {total}.'))

    def check_receivables(self, apply):
        count = 0
        for ctas in CtasCollect.objects.select_related('sale').iterator():
            balance, state = expected(ctas.debt, ctas.paymentsctacollect_set.values_list('valor', flat=True))
            if Decimal(ctas.saldo) != balance or bool(ctas.state) != state:
                count += 1
                self.stdout.write(
                    f'  Por cobrar #{ctas.id:06d} factura {ctas.sale.voucher_number_full}: deuda {ctas.debt}, saldo guardado {ctas.saldo} '
                    f'({"Adeuda" if ctas.state else "Pagada"}) -> debe ser {balance} ({"Adeuda" if state else "Pagada"})')
                if apply:
                    ctas.recalculate_details()
        return count

    def check_payables(self, apply):
        count = 0
        for debts in DebtsPay.objects.select_related('purchase').iterator():
            balance, state = expected(debts.debt, debts.paymentsdebtspay_set.values_list('valor', flat=True))
            if Decimal(debts.saldo) != balance or bool(debts.state) != state:
                count += 1
                self.stdout.write(
                    f'  Por pagar #{debts.id:06d} compra {debts.purchase.number}: deuda {debts.debt}, saldo guardado {debts.saldo} '
                    f'({"Adeuda" if debts.state else "Pagada"}) -> debe ser {balance} ({"Adeuda" if state else "Pagada"})')
                if apply:
                    debts.validate_debt()
        return count

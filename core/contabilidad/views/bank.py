from django.urls import reverse_lazy
from django.views.generic import FormView

from core.contabilidad.forms import BankAccountForm, BankAliasForm, BankMoveForm
from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.models import BankAccount, BankAlias
from core.contabilidad.services.posting import PeriodClosed, UnbalancedEntry, create_bank_move
from core.contabilidad.views.base import BaseCreateView, BaseDeleteView, BaseListView, BaseUpdateView, json_response
from core.security.mixins import GroupPermissionMixin


class BankAccountListView(BaseListView):
    template_name = 'contabilidad/bank/list.html'
    permission_required = 'view_bankaccount'
    model = BankAccount
    title = 'Cuentas Bancarias'

    @property
    def create_url(self):
        return reverse_lazy('contabilidad_bank_create')

    def get_queryset(self):
        return BankAccount.objects.select_related('account').order_by('bank_name', 'number')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['alias_url'] = reverse_lazy('contabilidad_bank_alias_list')
        context['move_url'] = reverse_lazy('contabilidad_bank_move')
        return context


class BankAccountCreateView(BaseCreateView):
    model = BankAccount
    form_class = BankAccountForm
    permission_required = 'add_bankaccount'
    title = 'Nueva cuenta bancaria'
    success_url = reverse_lazy('contabilidad_bank_list')


class BankAccountUpdateView(BaseUpdateView):
    model = BankAccount
    form_class = BankAccountForm
    permission_required = 'change_bankaccount'
    title = 'Edición de una cuenta bancaria'
    success_url = reverse_lazy('contabilidad_bank_list')


class BankAccountDeleteView(BaseDeleteView):
    model = BankAccount
    permission_required = 'delete_bankaccount'
    success_url = reverse_lazy('contabilidad_bank_list')

    def check_deletable(self, obj):
        if obj.lines.exists():
            raise ValueError('La cuenta bancaria ya tiene movimientos contables; desactívala en lugar de eliminarla.')

    def post(self, request, *args, **kwargs):
        # Se borra también la cuenta contable hija que se creó con la cuenta
        # bancaria (BankAccount.account es PROTECT, así que primero va esta).
        data = {}
        try:
            bank = self.get_object()
            self.check_deletable(bank)
            account = bank.account
            bank.delete()
            account.delete()
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)


class BankAliasListView(BaseListView):
    template_name = 'contabilidad/bank/alias_list.html'
    permission_required = 'view_bankalias'
    model = BankAlias
    title = 'Alias de Bancos'

    @property
    def create_url(self):
        return reverse_lazy('contabilidad_bank_alias_create')

    def get_queryset(self):
        return BankAlias.objects.select_related('bank_account__account').order_by('text')


class BankAliasCreateView(BaseCreateView):
    model = BankAlias
    form_class = BankAliasForm
    permission_required = 'add_bankalias'
    title = 'Nuevo alias de banco'
    success_url = reverse_lazy('contabilidad_bank_alias_list')


class BankAliasUpdateView(BaseUpdateView):
    model = BankAlias
    form_class = BankAliasForm
    permission_required = 'change_bankalias'
    title = 'Edición de un alias de banco'
    success_url = reverse_lazy('contabilidad_bank_alias_list')


class BankAliasDeleteView(BaseDeleteView):
    model = BankAlias
    permission_required = 'delete_bankalias'
    success_url = reverse_lazy('contabilidad_bank_alias_list')


class BankMoveView(AccountingEnabledMixin, GroupPermissionMixin, FormView):
    """Depósito de caja a banco, retiro, transferencia entre cuentas y
    comisiones: el POS no registra estos movimientos y sin ellos el banco y la
    caja contables no cuadran con la realidad."""
    template_name = 'contabilidad/bank/move.html'
    form_class = BankMoveForm
    permission_required = 'add_journalentry'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            form = self.get_form()
            if not form.is_valid():
                data['error'] = form.errors
            else:
                cd = form.cleaned_data
                entry = create_bank_move(
                    cd['kind'], cd['date'], cd['amount'], cd['bank_account'],
                    other_bank_account=cd.get('other_bank_account'), description=cd.get('description') or '', user=request.user,
                )
                data['entry'] = str(entry)
        except (UnbalancedEntry, PeriodClosed, ValueError) as e:
            data['error'] = str(e)
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['list_url'] = reverse_lazy('contabilidad_bank_list')
        context['title'] = 'Movimiento bancario'
        context['action'] = 'add'
        return context

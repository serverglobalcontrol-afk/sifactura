from django.urls import reverse_lazy

from core.contabilidad.forms import AccountForm
from core.contabilidad.models import Account
from core.contabilidad.views.base import BaseCreateView, BaseDeleteView, BaseListView, BaseUpdateView


class AccountListView(BaseListView):
    template_name = 'contabilidad/account/list.html'
    permission_required = 'view_account'
    model = Account
    title = 'Plan de Cuentas'

    @property
    def create_url(self):
        return reverse_lazy('contabilidad_account_create')

    def get_queryset(self):
        return Account.objects.select_related('parent').order_by('code')


class AccountCreateView(BaseCreateView):
    model = Account
    form_class = AccountForm
    permission_required = 'add_account'
    title = 'Nueva cuenta contable'
    success_url = reverse_lazy('contabilidad_account_list')


class AccountUpdateView(BaseUpdateView):
    model = Account
    form_class = AccountForm
    permission_required = 'change_account'
    title = 'Edición de una cuenta contable'
    success_url = reverse_lazy('contabilidad_account_list')


class AccountDeleteView(BaseDeleteView):
    model = Account
    permission_required = 'delete_account'
    success_url = reverse_lazy('contabilidad_account_list')

    def check_deletable(self, obj):
        if obj.is_system:
            raise ValueError('Las cuentas base del sistema no se pueden eliminar; desactívala si ya no la usas.')
        if obj.children.exists():
            raise ValueError('La cuenta tiene subcuentas; elimina o reubica primero las subcuentas.')
        if hasattr(obj, 'bank_account'):
            raise ValueError('Esta cuenta pertenece a una cuenta bancaria; elimina la cuenta bancaria desde Cuentas bancarias.')
        if obj.accountmapping_set.exists():
            raise ValueError('La cuenta está asignada a un rol contable (Configuración); asigna otra cuenta al rol antes de eliminarla.')

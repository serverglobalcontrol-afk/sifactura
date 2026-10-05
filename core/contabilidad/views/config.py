from django.urls import reverse_lazy
from django.views.generic import FormView

from core.contabilidad.forms import AccountingConfigForm
from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.views.base import json_response
from core.security.mixins import GroupPermissionMixin


class AccountingConfigView(AccountingEnabledMixin, GroupPermissionMixin, FormView):
    template_name = 'contabilidad/config/form.html'
    form_class = AccountingConfigForm
    permission_required = 'change_accountingconfig'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'edit':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['list_url'] = reverse_lazy('contabilidad_config')
        context['title'] = 'Configuración contable'
        context['action'] = 'edit'
        return context

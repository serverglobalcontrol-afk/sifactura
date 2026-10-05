from django.utils import timezone
from django.views.generic import TemplateView

from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.models import AccountingConfig, AccountingPeriod
from core.contabilidad.views.base import json_response
from core.security.mixins import GroupPermissionMixin


class PeriodListView(AccountingEnabledMixin, GroupPermissionMixin, TemplateView):
    """Cerrar un período bloquea cualquier cambio en sus asientos (los
    automáticos ya no se regeneran ni anulan). Reabrirlo lo permite de nuevo."""
    template_name = 'contabilidad/period/list.html'
    permission_required = 'view_accountingperiod'

    def _months(self):
        """Del mes de inicio de la contabilidad hasta el mes actual."""
        config = AccountingConfig.get()
        today = timezone.localdate()
        year, month = config.start_date.year, config.start_date.month
        while (year, month) <= (today.year, today.month):
            yield year, month
            month += 1
            if month == 13:
                year, month = year + 1, 1

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            action = request.POST['action']
            if action == 'search':
                for year, month in self._months():
                    AccountingPeriod.objects.get_or_create(year=year, month=month)
                data = [i.toJSON() for i in AccountingPeriod.objects.all()]
            elif action in ('close', 'reopen'):
                group = request.session.get('group')
                if group is None or not group.permissions.filter(codename='change_accountingperiod').exists():
                    raise ValueError('Tu perfil no cuenta con el permiso necesario para cambiar períodos.')
                period = AccountingPeriod.objects.get(pk=request.POST['id'])
                if action == 'close':
                    period.status, period.closed_at, period.closed_by = 'closed', timezone.now(), request.user
                else:
                    period.status, period.closed_at, period.closed_by = 'open', None, None
                period.save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Períodos Contables'
        return context

import json

from django.http import HttpResponse
from django.views.generic import FormView

from core.pos.choices import INVOICE_STATUS
from core.pos.models import Sale
from core.reports.forms import ReportForm
from core.security.mixins import GroupModuleMixin


class CanceledVouchersReportView(GroupModuleMixin, FormView):
    template_name = 'canceled_vouchers_report/report.html'
    form_class = ReportForm

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Sale.objects.filter(status=INVOICE_STATUS[3][0])
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Comprobantes Anulados'
        return context

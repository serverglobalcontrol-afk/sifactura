import json

from django.db.models import Sum
from django.http import HttpResponse
from django.views.generic import FormView

from core.pos.models import SaleDetail
from core.reports.forms import ReportForm
from core.security.mixins import GroupModuleMixin


class BestSellersReportView(GroupModuleMixin, FormView):
    template_name = 'best_sellers_report/report.html'
    form_class = ReportForm

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = SaleDetail.objects.filter()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(sale__date_joined__range=[start_date, end_date])
                rows = queryset.values('product__code', 'product__name').annotate(
                    cantidad=Sum('cant')
                ).order_by('-cantidad')
                for row in rows:
                    data.append({
                        'code': row['product__code'],
                        'name': row['product__name'],
                        'cantidad': row['cantidad'],
                    })
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Productos Más Vendidos'
        return context

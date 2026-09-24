import json

from django.db.models import Sum
from django.http import HttpResponse
from django.views.generic import FormView

from core.pos.models import SaleDetail
from core.reports.forms import ReportForm
from core.security.mixins import GroupModuleMixin


class CategoryReportView(GroupModuleMixin, FormView):
    template_name = 'category_report/report.html'
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
                rows = queryset.values('product__category__id', 'product__category__name').annotate(
                    cantidad=Sum('cant'),
                    total=Sum('total')
                ).order_by('-total')
                for row in rows:
                    data.append({
                        'category': row['product__category__name'],
                        'cantidad': row['cantidad'],
                        'total': float(row['total'] or 0),
                    })
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Ventas por Categoría'
        return context

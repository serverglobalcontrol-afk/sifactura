import json

from django.db.models import F
from django.http import HttpResponse
from django.views.generic import TemplateView

from core.pos.models import Product
from core.security.mixins import GroupModuleMixin


class LowStockReportView(GroupModuleMixin, TemplateView):
    template_name = 'low_stock_report/report.html'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                data = []
                # Productos inventariados cuyo stock ya llegó a su mínimo
                # configurado (stock_minimo); un stock en negativo siempre
                # cumple esta condición también.
                queryset = Product.objects.filter(inventoried=True, stock__lte=F('stock_minimo')).order_by('stock')
                for product in queryset:
                    data.append({
                        'code': product.code,
                        'name': product.name,
                        'stock': product.stock,
                        'stock_minimo': product.stock_minimo,
                    })
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Productos con Stock Bajo'
        return context

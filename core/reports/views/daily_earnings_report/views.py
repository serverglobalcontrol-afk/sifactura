import json

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.views.generic import FormView

from core.pos.models import SaleDetail
from core.reports.forms import ReportForm
from core.security.mixins import GroupModuleMixin

MONEY = DecimalField(max_digits=12, decimal_places=2)


class DailyEarningsReportView(GroupModuleMixin, FormView):
    template_name = 'daily_earnings_report/report.html'
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
                # Ganancia real del día: precio efectivamente facturado en
                # cada línea (ya neto de descuento, sin IVA -product__price
                # tampoco lo incluye-) contra el costo (precio de compra del
                # producto) al momento de generar el reporte. No es el precio
                # de lista (pvp) fijo: cada línea ya trae el precio que
                # realmente se cobró (público, distribuidor o tarjeta, según
                # el tipo de cliente de esa venta).
                cost_expression = Coalesce(Sum(F('product__price') * F('cant'), output_field=MONEY), 0.00, output_field=MONEY)
                revenue_expression = Coalesce(Sum('total'), 0.00, output_field=MONEY)
                rows = queryset.values('sale__date_joined').annotate(
                    units_sold=Coalesce(Sum('cant'), 0),
                    revenue=revenue_expression,
                    cost=cost_expression,
                ).order_by('-sale__date_joined')
                for row in rows:
                    revenue = float(row['revenue'])
                    cost = float(row['cost'])
                    profit = round(revenue - cost, 2)
                    margin = round((profit / revenue) * 100, 2) if revenue else 0.0
                    data.append({
                        'date_joined': row['sale__date_joined'].strftime('%Y-%m-%d'),
                        'units_sold': row['units_sold'],
                        'revenue': round(revenue, 2),
                        'cost': round(cost, 2),
                        'profit': profit,
                        'margin': margin,
                    })
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Ganancia Diaria'
        return context

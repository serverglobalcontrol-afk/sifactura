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
                        'category_id': row['product__category__id'],
                        'category': row['product__category__name'],
                        'cantidad': row['cantidad'],
                        'total': float(row['total'] or 0),
                    })
            elif action == 'search_detail':
                data = []
                category_id = request.POST['category_id']
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                queryset = SaleDetail.objects.filter(product__category_id=category_id)
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(sale__date_joined__range=[start_date, end_date])
                queryset = queryset.select_related('sale', 'product').order_by('-sale__date_joined', '-sale__voucher_number_full')
                for detail in queryset:
                    sale = detail.sale
                    product = detail.product
                    cost = float(product.price)
                    # Misma fórmula que Ganancia Diaria: lo realmente facturado
                    # en la línea (ya neto de descuento, sin IVA) menos el
                    # costo actual del producto -no el costo histórico de
                    # cuando se vendió, ni el pvp de lista si se vendió con
                    # otro precio (distribuidor, tarjeta, manual).
                    ganancia = round(float(detail.total) - (cost * detail.cant), 2)
                    data.append({
                        'date_joined': sale.date_joined.strftime('%Y-%m-%d'),
                        'voucher_number_full': sale.voucher_number_full,
                        'product': product.name,
                        'cant': detail.cant,
                        'cost': cost,
                        'pvp': float(product.pvp),
                        'ganancia': ganancia,
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

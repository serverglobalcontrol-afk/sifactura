import json

from django.http import HttpResponse
from django.views.generic import FormView

from core.pos.models import SaleDetail
from core.reports.forms import ProductSalesReportForm
from core.security.mixins import GroupModuleMixin


class ProductSalesReportView(GroupModuleMixin, FormView):
    template_name = 'product_sales_report/report.html'
    form_class = ProductSalesReportForm

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                data = []
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                product_id = json.loads(request.POST.get('product_id', '[]'))
                voucher_number = (request.POST.get('voucher_number') or '').strip()
                queryset = SaleDetail.objects.filter()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(sale__date_joined__range=[start_date, end_date])
                if product_id:
                    queryset = queryset.filter(product_id__in=product_id)
                if voucher_number:
                    queryset = queryset.filter(sale__voucher_number_full__icontains=voucher_number)
                queryset = queryset.select_related(
                    'product', 'sale', 'sale__receipt', 'sale__client', 'sale__client__user'
                ).order_by('-sale__date_joined', '-sale__voucher_number_full')
                for detail in queryset:
                    sale = detail.sale
                    data.append({
                        'date_joined': sale.date_joined.strftime('%Y-%m-%d'),
                        'voucher_number_full': sale.voucher_number_full,
                        'receipt': sale.receipt.name,
                        'client': sale.client.user.names,
                        'client_dni': sale.client.dni,
                        'product': {'code': detail.product.code, 'name': detail.product.name},
                        'cant': detail.cant,
                        'price': float(detail.price),
                        'total': float(detail.total),
                    })
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Ventas por Producto'
        return context

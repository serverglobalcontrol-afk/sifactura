import json

from django.db.models import Sum, Case, When, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.views.generic import FormView

from core.pos.models import Sale, Quotation
from core.reports.forms import SalePointOfSaleReportForm
from core.security.mixins import GroupModuleMixin


def payment_amount(payment_type):
    return Coalesce(
        Sum(Case(When(payment_type=payment_type, then='total'), output_field=FloatField())),
        0.00,
        output_field=FloatField(),
    )


class SalePointOfSaleReportView(GroupModuleMixin, FormView):
    template_name = 'sale_point_of_sale_report/report.html'
    form_class = SalePointOfSaleReportForm

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                employee_id = request.POST.get('employee')
                # Ventas diarias por cada Punto de Venta (empleado): sin
                # filtro de empleado es el reporte general de todos los
                # puntos de venta; con un empleado seleccionado, solo el de
                # ese punto de venta puntual.
                queryset = Sale.objects.filter()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                if employee_id:
                    queryset = queryset.filter(employee_id=employee_id)
                rows = queryset.values('date_joined', 'employee_id', 'employee__names').annotate(
                    ventas_efectivo=payment_amount('efectivo'),
                    ventas_transferencia=payment_amount('transferencia'),
                    ventas_tarjeta=payment_amount('tarjeta_credito'),
                    ventas_credito=payment_amount('credito'),
                    total=Coalesce(Sum('total'), 0.00, output_field=FloatField()),
                ).order_by('-date_joined', 'employee__names')
                for row in rows:
                    data.append({
                        'date_joined': row['date_joined'].strftime('%Y-%m-%d'),
                        'employee': {'id': row['employee_id'], 'names': row['employee__names']},
                        'ventas_efectivo': row['ventas_efectivo'],
                        'ventas_transferencia': row['ventas_transferencia'],
                        'ventas_tarjeta': row['ventas_tarjeta'],
                        'ventas_credito': row['ventas_credito'],
                        'total': row['total'],
                    })
            elif action == 'search_detail':
                data = []
                date_joined = request.POST['date_joined']
                employee_id = request.POST['employee_id']
                # Bitácora de gestiones del Punto de Venta ese día: incluye
                # tanto facturas (Sale) como cotizaciones (Quotation), con la
                # hora real (creation_date) en la que se registró cada una.
                gestiones = []
                sales = Sale.objects.filter(date_joined=date_joined, employee_id=employee_id)
                for sale in sales:
                    gestiones.append({
                        'fecha_hora': sale.creation_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'tipo': 'Factura',
                        'documento': sale.voucher_number_full,
                        'valor': float(sale.total),
                    })
                quotations = Quotation.objects.filter(date_joined=date_joined, employee_id=employee_id)
                for quotation in quotations:
                    gestiones.append({
                        'fecha_hora': quotation.creation_date.strftime('%Y-%m-%d %H:%M:%S'),
                        'tipo': 'Cotización',
                        'documento': quotation.voucher_number_full,
                        'valor': float(quotation.total),
                    })
                data = sorted(gestiones, key=lambda item: item['fecha_hora'])
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Ventas por Punto de Venta'
        return context

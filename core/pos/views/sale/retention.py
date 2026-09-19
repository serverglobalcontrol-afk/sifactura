import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import DeleteView, FormView
from django.views.generic.base import View

from core.pos.forms import Sale, Retention, INVOICE_STATUS
from core.pos.utilities.retention_xml_import import InvalidRetentionXMLError, parse_retention_xml
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class RetentionListView(GroupPermissionMixin, FormView):
    """Menú Facturación > Retenciones: historial de todos los comprobantes de
    retención registrados (sin importar desde qué venta), con los mismos
    filtros de fecha que el resto de listados."""
    template_name = 'retention/list.html'
    form_class = ReportForm
    permission_required = 'view_retention'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Retention.objects.all().order_by('-id')
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Retenciones'
        return context


class RetentionView(GroupPermissionMixin, View):
    """
    Endpoints AJAX (usados desde el modal "Registrar retención" del listado
    de Ventas) para capturar el comprobante de retención que un cliente
    entrega sobre una factura nuestra -no lo emitimos ni lo transmitimos al
    SRI, solo lo registramos como respaldo y para bajar el saldo pendiente
    de Cuentas por Cobrar (ver Retention.apply_to_ctas_collect).

    'parse_xml' solo lee el archivo y devuelve los datos para revisión -no
    guarda nada-; el registro final (manual o a partir de lo parseado) se
    hace siempre con 'add', igual que un usuario que llena el formulario a
    mano.
    """
    permission_required = 'add_retention'

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        data = {}
        try:
            if action == 'parse_xml':
                data = self.parse_xml(request)
            elif action == 'add':
                data = self.add(request)
            elif action == 'search':
                data = self.search(request)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except InvalidRetentionXMLError as e:
            data = {'error': str(e)}
        except Exception as e:
            data = {'error': str(e)}
        return HttpResponse(json.dumps(data), content_type='application/json')

    def parse_xml(self, request):
        if 'archive' not in request.FILES:
            raise InvalidRetentionXMLError('Debe seleccionar un archivo XML.')
        archive = request.FILES['archive']
        if not archive.name.lower().endswith('.xml'):
            raise InvalidRetentionXMLError('El archivo debe tener extensión .xml.')

        raw_xml = archive.read()
        parsed = parse_retention_xml(raw_xml)

        info = dict(parsed['info'])
        # fechaEmision del XML viene como dd/mm/aaaa; se intenta convertir para
        # precargar el campo de fecha, pero si el formato no coincide se deja
        # vacío y el usuario la ingresa a mano -no es motivo para rechazar todo
        # el XML, ya montos e identificación son lo importante.
        issue_date = ''
        raw_date = info.pop('issue_date_raw', '')
        if raw_date:
            parts = raw_date.split('/')
            if len(parts) == 3:
                day, month, year = parts
                issue_date = f'{year}-{month}-{day}'

        return {
            'info': info,
            'issue_date': issue_date,
            'iva_retained': float(parsed['iva_retained']),
            'income_tax_retained': float(parsed['income_tax_retained']),
            'total_retained': float(parsed['total_retained']),
        }

    def add(self, request):
        sale_id = request.POST.get('sale', '')
        try:
            sale = Sale.objects.get(pk=sale_id)
        except (Sale.DoesNotExist, ValueError, TypeError):
            raise InvalidRetentionXMLError('La venta seleccionada no existe.')

        if sale.status not in [INVOICE_STATUS[1][0], INVOICE_STATUS[2][0]]:
            raise InvalidRetentionXMLError('Solo se puede registrar una retención sobre una factura autorizada por el SRI.')

        document_number = request.POST.get('document_number', '').strip()
        if not document_number:
            raise InvalidRetentionXMLError('El número de comprobante es obligatorio.')
        if Retention.objects.filter(sale=sale, document_number=document_number).exists():
            raise InvalidRetentionXMLError(f'Ya existe una retención registrada para esta venta con el número "{document_number}".')

        issue_date_raw = request.POST.get('issue_date', '').strip()
        if not issue_date_raw:
            raise InvalidRetentionXMLError('La fecha de emisión es obligatoria.')
        try:
            issue_date = datetime.strptime(issue_date_raw, '%Y-%m-%d').date()
        except ValueError:
            raise InvalidRetentionXMLError('La fecha de emisión no es válida.')

        def to_decimal(raw, label):
            try:
                value = Decimal(raw or '0')
            except InvalidOperation:
                raise InvalidRetentionXMLError(f'El valor de {label} no es válido.')
            if value < 0:
                raise InvalidRetentionXMLError(f'El valor de {label} no puede ser negativo.')
            return value

        iva_retained = to_decimal(request.POST.get('iva_retained'), 'IVA retenido')
        income_tax_retained = to_decimal(request.POST.get('income_tax_retained'), 'Renta retenida')
        total_retained = iva_retained + income_tax_retained
        if total_retained <= 0:
            raise InvalidRetentionXMLError('El total retenido debe ser mayor a cero.')
        # No puede retenerse más de lo que vale la factura -señal segura de un
        # dato mal ingresado o un XML que no corresponde a esta venta.
        if total_retained > Decimal(str(sale.total)):
            raise InvalidRetentionXMLError(f'El total retenido (${total_retained}) no puede superar el total de la factura (${sale.total}).')

        with transaction.atomic():
            retention = Retention()
            retention.company = sale.company
            retention.sale = sale
            retention.created_by = request.user
            retention.issue_date = issue_date
            retention.document_number = document_number
            retention.access_code = request.POST.get('access_code', '').strip() or None
            retention.agent_ruc = request.POST.get('agent_ruc', '').strip() or None
            retention.agent_name = request.POST.get('agent_name', '').strip() or None
            retention.observations = request.POST.get('observations', '').strip() or None
            retention.iva_retained = iva_retained
            retention.income_tax_retained = income_tax_retained
            retention.total_retained = total_retained
            if 'archive' in request.FILES:
                retention.xml_file = request.FILES['archive']
            retention.save()
            retention.apply_to_ctas_collect(user=request.user)

        return retention.toJSON()

    def search(self, request):
        sale_id = request.POST.get('sale', '')
        data = []
        for i in Retention.objects.filter(sale_id=sale_id).order_by('-id'):
            data.append(i.toJSON())
        return data


class RetentionDeleteView(GroupPermissionMixin, DeleteView):
    model = Retention
    template_name = 'delete.html'
    success_url = reverse_lazy('sale_admin_list')
    permission_required = 'delete_retention'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context

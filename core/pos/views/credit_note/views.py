import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, FormView

from core.pos.forms import CreditNoteForm, CreditNote, CreditNoteDetail, Sale, Receipt, SaleDetail, VOUCHER_TYPE, INVOICE_STATUS, IDENTIFICATION_TYPE
from core.pos.utilities.sri import SRI
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class CreditNoteListView(GroupPermissionMixin, FormView):
    template_name = 'credit_note/admin/list.html'
    form_class = ReportForm
    permission_required = 'view_credit_note'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = CreditNote.objects.filter()
                if len(start_date) and len(end_date):
                    # date_joined es DateTimeField (hora real, no solo fecha):
                    # __date__range para no perder registros que no caigan
                    # justo a medianoche -mismo caso ya corregido en
                    # CashRegister.compute_breakdown().
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                for i in queryset.order_by('-id'):
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in CreditNoteDetail.objects.filter(credit_note_id=request.POST['id']):
                    data.append(i.toJSON())
            elif action == 'generate_invoice':
                credit_note = CreditNote.objects.get(pk=request.POST['id'])
                data = credit_note.generate_electronic_invoice()
                if 'error' in data:
                    SRI().create_voucher_errors(credit_note, data)
                elif not data.get('resp'):
                    # El SRI todavía no procesó la autorización (sin error real,
                    # solo pendiente); se avisa en vez de reportar éxito falso
                    # -mismo caso que Sale 'generate_invoice'.
                    data['error'] = 'El SRI todavía no ha autorizado esta nota de crédito. Intente nuevamente en unos minutos.'
            elif action == 'generate_pending_credit_notes':
                # Mismo botón/criterio que "Generar facturas pendientes" de
                # Ventas: reintenta manualmente las notas de crédito que
                # quedaron "Sin Autorizar" (el SRI no respondió a tiempo al
                # crearlas). Las de más de 24h se marcan aparte en vez de
                # seguir reintentando indefinidamente sin resultado.
                data = {'authorized': 0, 'failed': 0, 'stuck': 0, 'errors': []}
                sri = SRI()
                retry_cutoff = timezone.now() - timedelta(hours=24)
                pending = CreditNote.objects.filter(status=INVOICE_STATUS[0][0])
                for credit_note in pending:
                    if credit_note.date_joined < retry_cutoff:
                        data['stuck'] += 1
                        continue
                    result = credit_note.generate_electronic_invoice()
                    if 'error' in result:
                        sri.create_voucher_errors(credit_note, result)
                    if result.get('resp'):
                        data['authorized'] += 1
                    else:
                        data['failed'] += 1
                        data['errors'].append({'voucher_number_full': credit_note.voucher_number_full, 'error': result.get('error') or 'El SRI todavía no ha autorizado esta nota de crédito.'})
            elif action == 'send_invoice_by_email':
                credit_note = CreditNote.objects.get(pk=request.POST['id'])
                xml_electronic_signature = SRI()
                data = xml_electronic_signature.notify_by_email(instance=credit_note, company=credit_note.company, client=credit_note.sale.client)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Notas de Credito'
        context['create_url'] = reverse_lazy('credit_note_admin_create')
        return context


class CreditNoteCreateView(GroupPermissionMixin, CreateView):
    model = CreditNote
    template_name = 'credit_note/admin/create.html'
    form_class = CreditNoteForm
    success_url = reverse_lazy('credit_note_admin_list')
    permission_required = 'add_credit_note'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'add':
                idempotency_key = request.POST.get('idempotency_key') or None
                existing_credit_note = CreditNote.objects.filter(idempotency_key=idempotency_key).first() if idempotency_key else None
                if existing_credit_note:
                    # Ya se procesó una nota de crédito con esta misma llave (doble
                    # clic, reintento de red): se responde sin error para no crear
                    # un comprobante duplicado.
                    return HttpResponse(json.dumps(data), content_type='application/json')
                with transaction.atomic():
                    company = request.tenant.company
                    iva = float(company.iva) / 100
                    credit_note = CreditNote()
                    credit_note.idempotency_key = idempotency_key
                    credit_note.created_by = request.user
                    credit_note.refund_method = request.POST.get('refund_method', 'cash')
                    credit_note.date_joined = datetime.strptime(request.POST['date_joined'], '%Y-%m-%d').date()
                    credit_note.sale_id = int(request.POST['sale'])
                    # El SRI prohíbe anular o modificar con nota de crédito una
                    # factura emitida a "Consumidor Final" una vez transmitida
                    # (Resolución NAC-DGERCGC25-00000014, vigente desde 01/08/2025):
                    # la rechazaría en la recepción. search_sale ya excluye estas
                    # ventas del buscador, pero eso no evita una petición directa.
                    if credit_note.sale.client.identification_type == IDENTIFICATION_TYPE[-2][0]:
                        raise ValueError('El SRI no permite anular ni modificar con nota de crédito una factura emitida a Consumidor Final.')
                    # El mismo boletín limita la nota de crédito a un máximo de 12
                    # meses desde la fecha de emisión de la factura original.
                    if (datetime.now().date() - credit_note.sale.date_joined).days > 365:
                        raise ValueError('El SRI no permite emitir una nota de crédito sobre una factura con más de 12 meses de emitida.')
                    credit_note.motive = request.POST['motive']
                    credit_note.company = company
                    credit_note.environment_type = credit_note.company.environment_type
                    credit_note.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[1][0], establishment_code=credit_note.company.establishment_code, issuing_point_code=credit_note.company.issuing_point_code)
                    credit_note.voucher_number = credit_note.generate_voucher_number()
                    credit_note.voucher_number_full = credit_note.get_voucher_number_full()
                    credit_note.iva = iva
                    credit_note.create_electronic_invoice = 'create_electronic_invoice' in request.POST
                    credit_note.save()
                    for i in json.loads(request.POST['products']):
                        sale_detail = SaleDetail.objects.get(id=i['id'])
                        cant = int(i['quantity'])
                        if cant <= 0:
                            raise ValueError(f'Cantidad inválida para {sale_detail.product.name}')
                        # La cantidad devuelta nunca puede superar lo realmente vendido:
                        # se suma lo ya acreditado en notas de crédito anteriores para
                        # este mismo detalle de venta y se valida contra ese acumulado,
                        # en vez de confiar en la cantidad que manda el navegador.
                        already_credited = CreditNoteDetail.objects.filter(sale_detail_id=sale_detail.id).aggregate(result=Coalesce(Sum('cant'), 0, output_field=FloatField()))['result']
                        if already_credited + cant > sale_detail.cant:
                            available = sale_detail.cant - already_credited
                            raise ValueError(f'Cantidad a devolver excede lo disponible para {sale_detail.product.name} (disponible: {available})')
                        detail = CreditNoteDetail()
                        detail.credit_note_id = credit_note.id
                        detail.sale_detail_id = sale_detail.id
                        detail.product_id = sale_detail.product_id
                        detail.cant = cant
                        detail.price = float(i['price'])
                        detail.dscto = float(i['dscto']) / 100
                        detail.save()
                        credit_note.calculate_detail()
                        detail.product.register_movement(detail.cant, 'nota_credito', f'Nota de Crédito {credit_note.voucher_number_full}', user=request.user)
                    credit_note.calculate_invoice()
                    # La devolución de stock (ya aplicada arriba) es un hecho ya
                    # ocurrido, no algo condicionado a que el SRI responda -mismo
                    # criterio que 'create_credit_note' en sale/views.py-. Se
                    # confirma la venta como anulada aquí, dentro de esta misma
                    # transacción, y la autorización electrónica se intenta aparte:
                    # si el SRI tarda, la nota queda guardada como "Sin Autorizar"
                    # en vez de deshacerse todo el trámite.
                    if credit_note.create_electronic_invoice:
                        credit_note.sale.status = INVOICE_STATUS[3][0]
                        credit_note.sale.save()
                if credit_note.create_electronic_invoice:
                    data = credit_note.generate_electronic_invoice()
                    if not data['resp']:
                        if 'error' not in data:
                            # El SRI todavía no procesó la autorización (sin error
                            # real, solo pendiente); se avisa en vez de reportar
                            # éxito falso -mismo caso que 'generate_invoice'-, dejando
                            # claro que la nota SÍ quedó registrada.
                            data['error'] = 'La nota de crédito se registró correctamente, pero el SRI todavía no la ha autorizado. Puede reintentar la autorización desde el listado de Notas de Crédito.'
                        SRI().create_voucher_errors(credit_note, data)
            elif action == 'search_sale':
                data = []
                term = request.POST['term']
                for i in Sale.objects.filter(status__in=[INVOICE_STATUS[1][0], INVOICE_STATUS[2][0]]).filter(Q(voucher_number_full__icontains=term) | Q(voucher_number__icontains=term) | Q(client__user__names__icontains=term) | Q(client__dni__icontains=term) | Q(client__client_code__icontains=term)).exclude(client__identification_type=IDENTIFICATION_TYPE[-2][0]).order_by('voucher_number')[0:10]:
                    item = i.toJSON()
                    item['text'] = i.get_full_name()
                    item['detail'] = [d.toJSON({'quantity': d.cant, 'state': 0, 'total': 0.00}) for d in i.saledetail_set.all()]
                    data.append(item)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except Receipt.DoesNotExist:
            # No existe un comprobante "NOTA DE CRÉDITO" con el
            # establecimiento/punto de emisión ACTUAL de la compañía (ej.
            # alguien editó esos códigos en el perfil de la compañía después
            # de crearla, sin actualizar Bodega/Comprobantes a juego). Sin
            # este try/except esto tumbaba la página entera con un 500 -ver
            # incidente en mayashop/cybersolutions.
            messages.error(request, 'No existe un comprobante de Nota de Crédito configurado para el establecimiento/punto de emisión actual de la compañía. Revise Bodega > Comprobantes o contacte al administrador.')
            return HttpResponseRedirect(self.success_url)
        except Receipt.MultipleObjectsReturned:
            messages.error(request, 'Hay más de un comprobante de Nota de Crédito configurado para el mismo establecimiento/punto de emisión. Revise Bodega > Comprobantes y elimine el duplicado.')
            return HttpResponseRedirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = f'Nuevo registro de una Nota de Credito - {CreditNote().generate_voucher_number_full()}'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class CreditNoteDeleteView(GroupPermissionMixin, DeleteView):
    model = CreditNote
    template_name = 'delete.html'
    success_url = reverse_lazy('credit_note_admin_list')
    permission_required = 'delete_credit_note'

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


class CreditNoteClientListView(GroupPermissionMixin, FormView):
    template_name = 'credit_note/client/list.html'
    form_class = ReportForm
    permission_required = 'view_credit_note_client'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = CreditNote.objects.filter(sale__client__user_id=request.user.id)
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in CreditNoteDetail.objects.filter(credit_note_id=request.POST['id']):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Notas de Credito'
        return context

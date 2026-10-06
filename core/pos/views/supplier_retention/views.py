import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, FormView, TemplateView, UpdateView

from config import settings
from core.contabilidad.hooks import sync as sync_accounting
from core.pos.choices import INVOICE_STATUS, RETENTION_KIND
from core.pos.forms import RetentionConceptForm
from core.pos.models import Purchase, RetentionConcept, SupplierRetention, SupplierRetentionDetail
from core.pos.utilities.sri import SRI, error_text
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin

CENT = Decimal('0.01')


def json_response(data):
    return HttpResponse(json.dumps(data), content_type='application/json')


class SupplierRetentionListView(GroupPermissionMixin, FormView):
    """Retenciones EMITIDAS a proveedores (comprobante electrónico 07)."""
    template_name = 'supplier_retention/list.html'
    form_class = ReportForm
    permission_required = 'view_supplier_retention'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = SupplierRetention.objects.select_related('purchase', 'provider', 'receipt', 'created_by')
                start_date, end_date = request.POST.get('start_date'), request.POST.get('end_date')
                if start_date and end_date:
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                for i in queryset.order_by('-id'):
                    data.append(i.toJSON())
            elif action == 'search_detail':
                data = [i.toJSON() for i in SupplierRetentionDetail.objects.filter(retention_id=request.POST['id']).select_related('concept')]
            elif action == 'generate_invoice':
                retention = SupplierRetention.objects.get(pk=request.POST['id'])
                data = retention.generate_electronic_invoice()
                if 'error' in data:
                    SRI().create_voucher_errors(retention, data)
                elif not data.get('resp'):
                    data['error'] = 'El SRI todavía no ha autorizado esta retención. Intente nuevamente en unos minutos.'
            elif action == 'generate_pending':
                # Reintenta las retenciones que quedaron "Sin Autorizar" (el SRI no
                # respondió a tiempo); las de más de 24 h se marcan aparte.
                data = {'authorized': 0, 'failed': 0, 'stuck': 0, 'errors': []}
                sri = SRI()
                cutoff = timezone.now() - timedelta(hours=24)
                for retention in SupplierRetention.objects.filter(status=INVOICE_STATUS[0][0]):
                    if retention.date_joined < cutoff:
                        data['stuck'] += 1
                        continue
                    result = retention.generate_electronic_invoice()
                    if 'error' in result:
                        sri.create_voucher_errors(retention, result)
                    if result.get('resp'):
                        data['authorized'] += 1
                    else:
                        data['failed'] += 1
                        data['errors'].append({'voucher_number_full': retention.voucher_number_full, 'error': error_text(result.get('error'), 'El SRI todavía no ha autorizado esta retención.')})
            elif action == 'send_by_email':
                retention = SupplierRetention.objects.get(pk=request.POST['id'])
                if retention.status not in (INVOICE_STATUS[1][0], INVOICE_STATUS[2][0]):
                    raise ValueError('Solo se puede enviar una retención ya autorizada por el SRI.')
                data = SRI().notify_retention_by_email(instance=retention)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Retenciones emitidas a proveedores'
        context['create_url'] = reverse_lazy('purchase_list')
        context['list_url'] = reverse_lazy('supplier_retention_list')
        return context


def _decimal(value, label):
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        raise ValueError(f'El valor de {label} no es válido.')


class SupplierRetentionCreateView(GroupPermissionMixin, TemplateView):
    """Emitir la retención de una compra: se eligen los conceptos de renta y de
    IVA, y se emite, firma y autoriza el comprobante electrónico."""
    template_name = 'supplier_retention/create.html'
    permission_required = 'add_supplier_retention'

    def get_purchase(self):
        return Purchase.objects.select_related('provider').get(pk=self.request.GET.get('purchase') or self.request.POST.get('purchase'))

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            action = request.POST['action']
            if action == 'add':
                data = self.add(request)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except SupplierRetentionError as e:
            data = {'error': str(e)}
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def add(self, request):
        company = request.tenant.company
        if not company.is_retention_agent:
            raise SupplierRetentionError('Esta empresa no está registrada como agente de retención (Editar Compañía > Agente de Retención).')
        idempotency_key = request.POST.get('idempotency_key') or None
        existing = SupplierRetention.objects.filter(idempotency_key=idempotency_key).first() if idempotency_key else None
        if existing:
            return {'print_url': existing.get_pdf_authorized() or '', 'duplicate': True}
        purchase = self.get_purchase()
        items = json.loads(request.POST['items'])
        if not items:
            raise SupplierRetentionError('Agrega al menos un concepto de retención.')
        rows = []
        for item in items:
            concept = RetentionConcept.objects.get(pk=item['concept'], active=True)
            base = _decimal(item['base'], 'la base imponible')
            percentage = _decimal(item['percentage'], 'el porcentaje')
            if base <= 0:
                raise SupplierRetentionError(f'La base imponible de {concept.code} debe ser mayor a cero.')
            if percentage < 0 or percentage > 100:
                raise SupplierRetentionError(f'El porcentaje de {concept.code} no es válido.')
            # La base no puede superar lo que sustenta la compra.
            limit = Decimal(purchase.total_iva) if concept.kind == RETENTION_KIND[1][0] else Decimal(purchase.subtotal)
            if base > limit:
                raise SupplierRetentionError(f'La base de {concept.code} (${base}) no puede superar {"el IVA" if concept.kind == RETENTION_KIND[1][0] else "el subtotal"} de la compra (${limit}).')
            if concept.percentage is not None and percentage != Decimal(concept.percentage).quantize(CENT):
                raise SupplierRetentionError(f'El porcentaje de {concept.code} debe ser {concept.percentage}% según el catálogo. Si cambió, actualízalo en Conceptos de retención.')
            rows.append((concept, base, percentage, (base * percentage / Decimal('100')).quantize(CENT, rounding=ROUND_HALF_UP)))
        if sum((r[3] for r in rows), Decimal('0')) <= 0:
            raise SupplierRetentionError('El total retenido debe ser mayor a cero.')

        with transaction.atomic():
            # Se bloquea la serie: dos retenciones simultáneas no pueden recibir el mismo número.
            receipt = SupplierRetention.get_receipt_for(company, lock=True)
            retention = SupplierRetention()
            retention.idempotency_key = idempotency_key
            retention.company = company
            retention.purchase = purchase
            retention.provider = purchase.provider
            retention.receipt = receipt
            retention.created_by = request.user
            retention.environment_type = company.environment_type
            retention.voucher_number = retention.generate_voucher_number()
            retention.voucher_number_full = retention.get_voucher_number_full()
            retention.observations = (request.POST.get('observations') or '')[:300]
            retention.save()
            for concept, base, percentage, value in rows:
                SupplierRetentionDetail.objects.create(retention=retention, concept=concept, base=base, percentage=percentage, value=value)
            retention.calculate_totals()
            retention.apply_to_debts_pay(user=request.user)
            sync_accounting('issued_retention', retention.pk)
            sync_accounting('purchase', purchase.pk)
        # El trámite ante el SRI va FUERA de la transacción: si el SRI tarda, la
        # retención queda guardada "Sin Autorizar" y se reintenta desde el listado.
        result = retention.generate_electronic_invoice()
        if not result.get('resp'):
            error = result.get('error')
            SRI().create_voucher_errors(retention, result) if 'error' in result else None
            return {
                'warning': (error if isinstance(error, str) else (error.get('message') if isinstance(error, dict) else None)) or 'La retención quedó registrada, pero el SRI todavía no la autorizó. Puedes reintentar desde el listado de Retenciones emitidas.',
                'retention': retention.pk,
            }
        return {'print_url': result.get('print_url') or '', 'retention': retention.pk}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        purchase = self.get_purchase()
        company = self.request.tenant.company
        context['title'] = f'Emitir retención - compra {purchase.number}'
        context['purchase'] = purchase
        context['list_url'] = reverse_lazy('supplier_retention_list')
        context['action'] = 'add'
        context['is_agent'] = company.is_retention_agent
        try:
            receipt = SupplierRetention.get_receipt_for(company)
            context['next_number'] = f'{receipt.establishment_code}-{receipt.issuing_point_code}-{int(receipt.get_sequence()) + 1:09d}'
        except ValueError as e:
            context['receipt_error'] = str(e)
        context['ready_error'] = ''
        if len(purchase.number) != 15 or not purchase.number.isdigit():
            context['ready_error'] = f'El número de la compra ({purchase.number}) debe ser el de la factura del proveedor: 15 dígitos.'
        elif purchase.voucher_type == '01' and not purchase.authorization_number and settings.RETENTION_REQUIRE_SUPPLIER_AUTHORIZATION:
            context['ready_error'] = 'La compra no tiene el número de autorización del proveedor.'
        context['existing'] = SupplierRetention.objects.filter(purchase=purchase).count()
        context['concepts'] = json.dumps([i.toJSON() for i in RetentionConcept.objects.filter(active=True).order_by('code')])
        context['purchase_json'] = json.dumps({'subtotal': float(purchase.subtotal), 'total_iva': float(purchase.total_iva), 'total': float(purchase.total)})
        return context


class SupplierRetentionError(ValueError):
    pass


class SupplierRetentionDeleteView(GroupPermissionMixin, DeleteView):
    model = SupplierRetention
    template_name = 'delete.html'
    success_url = reverse_lazy('supplier_retention_list')
    permission_required = 'delete_supplier_retention'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context


# ---- Catálogo de conceptos de retención ----

class RetentionConceptListView(GroupPermissionMixin, TemplateView):
    template_name = 'retention_concept/list.html'
    permission_required = 'view_retention_concept'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'search':
                data = [i.toJSON() for i in RetentionConcept.objects.all()]
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Conceptos de retención'
        context['create_url'] = reverse_lazy('retention_concept_create')
        return context


class RetentionConceptCreateView(GroupPermissionMixin, CreateView):
    model = RetentionConcept
    template_name = 'retention_concept/create.html'
    form_class = RetentionConceptForm
    success_url = reverse_lazy('retention_concept_list')
    permission_required = 'add_retention_concept'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'add':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['list_url'] = self.success_url
        context['title'] = 'Nuevo concepto de retención'
        context['action'] = 'add'
        return context


class RetentionConceptUpdateView(GroupPermissionMixin, UpdateView):
    model = RetentionConcept
    template_name = 'retention_concept/create.html'
    form_class = RetentionConceptForm
    success_url = reverse_lazy('retention_concept_list')
    permission_required = 'change_retention_concept'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'edit':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['list_url'] = self.success_url
        context['title'] = 'Edición de un concepto de retención'
        context['action'] = 'edit'
        return context


class RetentionConceptDeleteView(GroupPermissionMixin, DeleteView):
    model = RetentionConcept
    template_name = 'delete.html'
    success_url = reverse_lazy('retention_concept_list')
    permission_required = 'delete_retention_concept'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            from django.db.models import ProtectedError
            data['error'] = 'No se puede eliminar: ya se usó en una retención. Desactívalo en lugar de eliminarlo.' if isinstance(e, ProtectedError) else str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context

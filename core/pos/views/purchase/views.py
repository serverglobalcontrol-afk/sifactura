import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, FormView

from core.contabilidad.hooks import sync as sync_accounting
from core.pos.forms import PurchaseForm, Purchase, PurchaseDetail, Product, Provider, DebtsPay, ProviderForm, PAYMENT_TYPE, CashRegister
from core.pos.utilities.purchase_xml_import import InvalidPurchaseXMLError, parse_supplier_invoice_xml
from core.pos.choices import PURCHASE_VOUCHER_TYPE, TAX_SUPPORT, PURCHASE_TAX_TYPE, PAYMENT_METHOD, VALID_IVA_PERCENTS
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


def _choice(value, choices, default, label):
    """Valida que `value` sea uno de los códigos de `choices` (vacío -> default)."""
    value = (value or '').strip() or default
    if value not in [c[0] for c in choices]:
        raise ValueError(f'{label} no es válido.')
    return value


def _line_tax(item, company):
    """(tax_type, iva_percent) de una línea del detalle: el tipo viene del
    navegador, pero la tarifa se valida contra las tarifas de IVA conocidas y,
    si la línea no trae una, se usa la de la empresa."""
    tax_type = _choice(item.get('tax'), PURCHASE_TAX_TYPE, PURCHASE_TAX_TYPE[0][0], 'El tipo de IVA')
    if tax_type != 'iva':
        return tax_type, Decimal('0.00')
    try:
        percent = Decimal(str(item.get('iva_percent', company.iva))).quantize(Decimal('0.01'))
    except InvalidOperation:
        raise ValueError('La tarifa de IVA de una línea no es válida.')
    if percent not in [Decimal(p) for p in VALID_IVA_PERCENTS]:
        raise ValueError(f'La tarifa de IVA {percent}% no es una tarifa válida.')
    return tax_type, percent


def _validate_uploaded_xml(request, purchase):
    """Si la compra se registró importando el XML del proveedor, vuelve a
    leerlo y validarlo EN EL SERVIDOR (nunca se confía en lo que el navegador
    dice haber leído) y lo cruza con lo que se está guardando. Devuelve lo
    leído, o None si no se subió ningún XML. Lanza ValueError si algo no cuadra."""
    xml_upload = request.FILES.get('xml_file')
    if xml_upload is None:
        return None
    raw = xml_upload.read()
    xml_upload.seek(0)
    parsed = parse_supplier_invoice_xml(raw)
    info = parsed['info']
    provider = Provider.objects.get(pk=purchase.provider_id)
    if provider.ruc != info['ruc']:
        raise ValueError(f'El proveedor seleccionado (RUC {provider.ruc}) no es el emisor del XML (RUC {info["ruc"]}).')
    if purchase.number != info['invoice_number']:
        raise ValueError(f'El número de factura ({purchase.number}) no coincide con el del XML ({info["invoice_number"]}).')
    if Purchase.objects.filter(access_key=info['clave_acceso']).exists():
        raise ValueError('Esta factura ya fue registrada antes (misma clave de acceso).')
    return parsed


def _store_xml_history(purchase, parsed, xml_upload):
    """Guarda en la compra el archivo original y lo leído del XML (historial)."""
    info = parsed['info']
    purchase.access_key = info['clave_acceso']
    purchase.authorization_number = info['authorization_number']
    purchase.voucher_type = '01'
    if info['issue_date']:
        purchase.issue_date = datetime.strptime(info['issue_date'], '%Y-%m-%d').date()
    if info['authorization_date']:
        try:
            purchase.authorization_date = datetime.fromisoformat(info['authorization_date'])
        except ValueError:
            purchase.authorization_date = None
    purchase.xml_data = {
        'ruc': info['ruc'], 'razon_social': info['razon_social'], 'invoice_number': info['invoice_number'],
        'issue_date': info['issue_date'], 'authorized': info['authorized'],
        'total_without_tax': info['total_without_tax'], 'total_iva': info['total_iva'], 'total': info['total'],
        'lines': len(parsed['lines']), 'warnings': parsed['warnings'],
    }
    xml_upload.seek(0)
    purchase.xml_file.save(f'{info["clave_acceso"]}.xml', xml_upload, save=False)


def _check_xml_totals(purchase, parsed):
    """El total que se está registrando debe coincidir con el del XML (con la
    tolerancia por redondeo): si no, alguien cambió líneas o IVA después de
    importar y la compra ya no sería fiel a la factura del proveedor."""
    declared = parsed['info']['total']
    if declared is None:
        return
    tolerance = Decimal('0.02') * len(parsed['lines']) + Decimal('0.01')
    if abs(Decimal(purchase.total) - Decimal(str(declared))) > tolerance:
        raise ValueError(f'El total de la compra (${purchase.total}) no coincide con el de la factura XML (${declared:.2f}). No modifiques cantidades, precios ni IVA de una factura importada del XML.')


class PurchaseListView(GroupPermissionMixin, FormView):
    template_name = 'purchase/list.html'
    form_class = ReportForm
    permission_required = 'view_purchase'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Purchase.objects.filter().select_related('provider')
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in PurchaseDetail.objects.filter(purchase_id=request.POST['id']).select_related('product__category'):
                    data.append(i.toJSON())
            elif action == 'update_voucher_data':
                data = self.update_voucher_data(request)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def update_voucher_data(self, request):
        """Corrige los datos del comprobante del proveedor (número, tipo, sustento,
        fecha de emisión, autorización y forma de pago) SIN tocar montos, stock,
        cuentas por pagar ni caja: son los datos que pide el ATS y que a veces se
        registran incompletos."""
        from core.pos.choices import INVOICE_STATUS
        from core.pos.models import SupplierRetention
        group = request.session.get('group')
        if group is None or not group.permissions.filter(codename='add_purchase').exists():
            raise ValueError('Tu perfil no tiene permiso para modificar compras.')
        purchase = Purchase.objects.get(pk=request.POST['id'])
        if SupplierRetention.objects.filter(purchase=purchase, status__in=(INVOICE_STATUS[1][0], INVOICE_STATUS[2][0])).exists():
            raise ValueError('Esta compra ya tiene una retención autorizada por el SRI: sus datos ya no se pueden modificar.')
        number = (request.POST.get('number') or '').strip()
        voucher_type = request.POST.get('voucher_type') or ''
        tax_support = request.POST.get('tax_support') or ''
        payment_method = request.POST.get('payment_method') or ''
        authorization = (request.POST.get('authorization_number') or '').strip()
        try:
            issue_date = datetime.strptime(request.POST.get('issue_date') or '', '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('La fecha de emisión del comprobante no es válida.')
        if len(number) != 15 or not number.isdigit():
            raise ValueError('El número debe tener 15 dígitos: establecimiento (3) + punto de emisión (3) + secuencial (9). Ej: 001002000004521.')
        if Purchase.objects.filter(number=number).exclude(pk=purchase.pk).exists():
            raise ValueError(f'Ya existe otra compra registrada con el número {number}.')
        if voucher_type not in dict(PURCHASE_VOUCHER_TYPE):
            raise ValueError('Elige un tipo de comprobante válido.')
        if tax_support not in dict(TAX_SUPPORT):
            raise ValueError('Elige un sustento tributario válido.')
        if payment_method not in dict(PAYMENT_METHOD):
            raise ValueError('Elige una forma de pago válida.')
        if authorization and (not authorization.isdigit() or not 10 <= len(authorization) <= 49):
            raise ValueError('El número de autorización debe tener solo dígitos (entre 10 y 49) o quedar vacío.')
        registered = purchase.date_joined.date()
        if issue_date > registered:
            raise ValueError(f'La fecha de emisión del comprobante ({issue_date:%d/%m/%Y}) no puede ser posterior a la fecha de registro de la compra ({registered:%d/%m/%Y}).')
        if purchase.xml_file and (number != purchase.number or authorization != purchase.authorization_number or issue_date != purchase.issue_date or voucher_type != purchase.voucher_type):
            raise ValueError('Esta compra se registró desde el XML validado del proveedor: su número, tipo, fecha y autorización no se modifican (solo el sustento tributario y la forma de pago).')
        with transaction.atomic():
            purchase.number = number
            purchase.voucher_type = voucher_type
            purchase.tax_support = tax_support
            purchase.payment_method = payment_method
            purchase.authorization_number = authorization
            purchase.issue_date = issue_date
            purchase.save(update_fields=['number', 'voucher_type', 'tax_support', 'payment_method', 'authorization_number', 'issue_date'])
            sync_accounting('purchase', purchase.pk)
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['voucher_types'] = PURCHASE_VOUCHER_TYPE
        context['tax_supports'] = TAX_SUPPORT
        context['payment_methods'] = PAYMENT_METHOD
        context['title'] = 'Listado de Compras'
        context['create_url'] = reverse_lazy('purchase_create')
        # El botón "Emitir retención" solo se ofrece a empresas agente de
        # retención que además tienen permiso para emitirlas.
        group = self.request.session.get('group')
        context['can_issue_retention'] = bool(
            self.request.tenant.company.is_retention_agent and group is not None
            and group.permissions.filter(codename='add_supplier_retention').exists())
        return context


class PurchaseCreateView(GroupPermissionMixin, CreateView):
    model = Purchase
    template_name = 'purchase/create.html'
    form_class = PurchaseForm
    success_url = reverse_lazy('purchase_list')
    permission_required = 'add_purchase'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'add':
                idempotency_key = request.POST.get('idempotency_key') or None
                existing_purchase = Purchase.objects.filter(idempotency_key=idempotency_key).first() if idempotency_key else None
                if existing_purchase:
                    # Ya se procesó una compra con esta misma llave (doble clic,
                    # reintento de red): se responde sin error para no crear un
                    # registro duplicado.
                    return HttpResponse(json.dumps(data), content_type='application/json')
                purchase_company = request.tenant.company
                with transaction.atomic():
                    purchase = Purchase()
                    purchase.idempotency_key = idempotency_key
                    purchase.number = request.POST['number']
                    purchase.provider_id = int(request.POST['provider'])
                    purchase.payment_type = request.POST['payment_type']
                    purchase.date_joined = request.POST['date_joined']
                    purchase.created_by = request.user
                    # Datos del comprobante del proveedor (los exige el ATS).
                    purchase.voucher_type = _choice(request.POST.get('voucher_type'), PURCHASE_VOUCHER_TYPE, PURCHASE_VOUCHER_TYPE[0][0], 'El tipo de comprobante')
                    purchase.tax_support = _choice(request.POST.get('tax_support'), TAX_SUPPORT, TAX_SUPPORT[5][0], 'El sustento tributario')
                    purchase.payment_method = _choice(request.POST.get('payment_method'), PAYMENT_METHOD, PAYMENT_METHOD[0][0], 'La forma de pago')
                    issue_raw = (request.POST.get('issue_date') or '').strip()
                    try:
                        purchase.issue_date = datetime.strptime(issue_raw, '%Y-%m-%d').date() if issue_raw else datetime.strptime(request.POST['date_joined'], '%Y-%m-%d').date()
                    except ValueError:
                        raise ValueError('La fecha de emisión del comprobante no es válida.')
                    authorization = (request.POST.get('authorization_number') or '').strip()
                    if authorization and (not authorization.isdigit() or not 3 <= len(authorization) <= 49):
                        raise ValueError('El número de autorización debe tener solo dígitos (entre 3 y 49).')
                    purchase.authorization_number = authorization
                    purchase.provider_id = int(request.POST['provider'])
                    xml_parsed = _validate_uploaded_xml(request, purchase)
                    if xml_parsed is not None:
                        _store_xml_history(purchase, xml_parsed, request.FILES['xml_file'])
                    # Efectivo disponible ANTES de registrar esta compra (después ya
                    # estaría descontada del cuadre de caja). Solo aplica a una compra
                    # en efectivo de hoy: es la regla que ya rige para pagos y gastos.
                    available_cash = None
                    if purchase.payment_type == PAYMENT_TYPE[0][0] and datetime.strptime(request.POST['date_joined'], '%Y-%m-%d').date() == date.today():
                        available_cash = CashRegister.get_available_cash(request.user)
                    purchase.save()

                    for i in json.loads(request.POST['products']):
                        product = Product.objects.get(pk=i['id'])
                        cant = int(i['cant'])
                        price = float(i['price'])
                        if cant <= 0:
                            raise ValueError(f'Cantidad inválida para {product.name}')
                        if price < 0:
                            raise ValueError(f'Precio inválido para {product.name}')
                        detail = PurchaseDetail()
                        detail.purchase_id = purchase.id
                        detail.product_id = product.id
                        detail.cant = cant
                        detail.price = price
                        detail.subtotal = detail.cant * float(detail.price)
                        detail.tax_type, detail.iva_percent = _line_tax(i, purchase_company)
                        detail.save()
                        detail.product.register_movement(detail.cant, 'compra', f'Compra #{purchase.id} ({purchase.number})', user=request.user)

                    purchase.calculate_invoice()
                    if xml_parsed is not None:
                        _check_xml_totals(purchase, xml_parsed)

                    if available_cash is not None and float(purchase.total) > available_cash:
                        raise ValueError(f'No hay suficiente efectivo en caja para esta compra (disponible: ${available_cash:.2f}, se necesita: ${float(purchase.total):.2f}). Registra un Ingreso a caja desde Administrativo > Ingresos para cubrir la diferencia, o registra la compra a crédito.')

                    if purchase.payment_type == PAYMENT_TYPE[1][0]:
                        purchase.end_credit = request.POST['end_credit']
                        purchase.save()
                        debtspay = DebtsPay()
                        debtspay.purchase_id = purchase.id
                        debtspay.date_joined = purchase.date_joined
                        debtspay.end_date = purchase.end_credit
                        # La deuda con el proveedor es el TOTAL de la factura (con IVA).
                        debtspay.debt = purchase.total
                        debtspay.saldo = purchase.total
                        debtspay.save()
                    sync_accounting('purchase', purchase.pk)
            elif action == 'search_product':
                data = []
                ids = json.loads(request.POST['ids'])
                term = request.POST['term']
                queryset = Product.objects.filter(inventoried=True).exclude(id__in=ids).order_by('name')
                if len(term):
                    queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
                    queryset = queryset[0:10]
                for i in queryset:
                    item = i.toJSON()
                    item['value'] = i.get_full_name()
                    data.append(item)
            elif action == 'search_provider':
                data = []
                for i in Provider.objects.filter(name__icontains=request.POST['term']).order_by('name')[0:10]:
                    data.append(i.toJSON())
            elif action == 'validate_provider':
                data = {'valid': True}
                queryset = Provider.objects.all()
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                if pattern == 'name':
                    data['valid'] = not queryset.filter(name__iexact=parameter).exists()
                elif pattern == 'ruc':
                    data['valid'] = not queryset.filter(ruc=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(email=parameter).exists()
            elif action == 'validate_purchase':
                data = {'valid': True}
                pattern = request.POST['pattern']
                if pattern == 'number':
                    data['valid'] = not Purchase.objects.filter(number=request.POST['number']).exists()
            elif action == 'create_provider':
                form = ProviderForm(request.POST)
                data = form.save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de una Compra'
        context['frmProvider'] = ProviderForm()
        context['list_url'] = self.success_url
        context['action'] = 'add'
        # Tarifa de IVA de la empresa (%), para precalcular el IVA de cada
        # línea en el formulario; el servidor la valida igual.
        context['company_iva'] = float(self.request.tenant.company.iva)
        # Efectivo que hay ahora en la caja del usuario: una compra en efectivo
        # no puede superarlo (misma regla que pagos a proveedores y gastos).
        context['available_cash'] = CashRegister.get_available_cash(self.request.user)
        return context


class PurchaseDeleteView(GroupPermissionMixin, DeleteView):
    model = Purchase
    template_name = 'delete.html'
    success_url = reverse_lazy('purchase_list')
    permission_required = 'delete_purchase'

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

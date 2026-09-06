import base64
import json
from decimal import Decimal
from io import BytesIO

import qrcode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView

from config import settings
from core.pos.choices import CUSTOMER_TYPE
from core.pos.forms import SaleForm, ClientForm, ClientUserForm, Sale, SaleDetail, Client, Product, Receipt, CreditNote, CreditNoteDetail, CtasCollect, INVOICE_STATUS, VOUCHER_TYPE
from core.pos.utilities import printer
from core.pos.utilities.sri import SRI
from core.pos.utilities.utils import money
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class SaleListView(GroupPermissionMixin, FormView):
    template_name = 'sale/admin/list.html'
    form_class = ReportForm
    permission_required = 'view_sale'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Sale.objects.filter()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in SaleDetail.objects.filter(sale_id=request.POST['id']):
                    data.append(i.toJSON())
            elif action == 'generate_invoice':
                sale = Sale.objects.get(pk=request.POST['id'])
                data = sale.generate_electronic_invoice()
                if 'error' in data:
                    SRI().create_voucher_errors(sale, data)
            elif action == 'create_credit_note':
                with transaction.atomic():
                    sale = Sale.objects.get(pk=request.POST['id'])
                    company = sale.company
                    iva = float(company.iva) / 100
                    credit_note = CreditNote()
                    credit_note.sale_id = sale.id
                    credit_note.motive = F'NOTA DE CREDITO DE LA VENTA {sale.voucher_number_full}'
                    credit_note.company = company
                    credit_note.environment_type = credit_note.company.environment_type
                    credit_note.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[1][0], establishment_code=sale.company.establishment_code, issuing_point_code=sale.company.issuing_point_code)
                    credit_note.voucher_number = credit_note.generate_voucher_number()
                    credit_note.voucher_number_full = credit_note.get_voucher_number_full()
                    credit_note.iva = iva
                    credit_note.save()
                    for sale_detail in sale.saledetail_set.all():
                        detail = CreditNoteDetail()
                        detail.credit_note_id = credit_note.id
                        detail.sale_detail_id = sale_detail.id
                        detail.product_id = sale_detail.product_id
                        detail.cant = sale_detail.cant
                        detail.price = sale_detail.price
                        detail.dscto = sale_detail.dscto
                        detail.save()
                        credit_note.calculate_detail()
                        detail.product.register_movement(detail.cant, 'nota_credito', f'Nota de Crédito {credit_note.voucher_number_full} (anulación de venta {sale.voucher_number_full})', user=request.user)
                    credit_note.calculate_invoice()
                    data = credit_note.generate_electronic_invoice()
                    if not data['resp']:
                        transaction.set_rollback(True)
                    else:
                        sale.status = INVOICE_STATUS[3][0]
                        sale.save()
                if 'error' in data:
                    SRI().create_voucher_errors(credit_note, data)
            elif action == 'send_invoice_by_email':
                sale = Sale.objects.get(pk=request.POST['id'])
                xml_electronic_signature = SRI()
                data = xml_electronic_signature.notify_by_email(instance=sale, company=sale.company, client=sale.client)
            elif action == 'search_client':
                data = []
                term = request.POST['term']
                for i in Client.objects.filter(Q(user__names__icontains=term) | Q(dni__icontains=term)).order_by('user__names')[0:10]:
                    data.append(i.toJSON())
            elif action == 'update_client':
                sale = Sale.objects.get(pk=request.POST['id'])
                if sale.status in [INVOICE_STATUS[1][0], INVOICE_STATUS[2][0]]:
                    raise Exception('No se puede cambiar el cliente de una factura ya autorizada por el SRI')
                sale.client_id = int(request.POST['client'])
                sale.save()
                data = sale.toJSON()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Ventas'
        context['create_url'] = reverse_lazy('sale_admin_create')
        return context


class SaleCreateView(GroupPermissionMixin, CreateView):
    model = Sale
    template_name = 'sale/admin/create.html'
    form_class = SaleForm
    success_url = reverse_lazy('sale_admin_list')
    permission_required = 'add_sale'

    def get_first_final_consumer(self):
        client = Client.objects.filter(dni='9999999999999').first()
        return client.toJSON() if client else dict()

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'add':
                idempotency_key = request.POST.get('idempotency_key') or None
                existing_sale = Sale.objects.filter(idempotency_key=idempotency_key).first() if idempotency_key else None
                if existing_sale:
                    # Ya se procesó una venta con esta misma llave (doble clic,
                    # reintento de red): se devuelve el resultado de esa venta
                    # en vez de crear un comprobante duplicado.
                    data = {'print_url': str(reverse_lazy('sale_admin_print_invoice', kwargs={'pk': existing_sale.id}))}
                    return HttpResponse(json.dumps(data), content_type='application/json')
                with transaction.atomic():
                    sale = Sale()
                    sale.idempotency_key = idempotency_key
                    sale.date_joined = request.POST['date_joined']
                    sale.company = request.tenant.company
                    sale.environment_type = sale.company.environment_type
                    requested_voucher_type = request.POST['receipt']
                    if requested_voucher_type == VOUCHER_TYPE[2][0] and not sale.company.enable_ticket_sale:
                        raise Exception('El Ticket de Venta no está habilitado para esta compañía')
                    if requested_voucher_type == VOUCHER_TYPE[4][0] and not sale.company.enable_purchase_settlement:
                        raise Exception('La Liquidación de Compra no está habilitada para esta compañía')
                    sale.receipt = Receipt.objects.get(voucher_type=requested_voucher_type, establishment_code=sale.company.establishment_code, issuing_point_code=sale.company.issuing_point_code)
                    sale.voucher_number = sale.generate_voucher_number()
                    sale.voucher_number_full = sale.get_voucher_number_full()
                    sale.employee_id = request.user.id
                    sale.client_id = int(request.POST['client'])
                    sale.payment_type = request.POST['payment_type']
                    sale.additional_info = json.loads(request.POST['additional_info'])
                    sale.iva = float(sale.company.iva) / 100
                    sale.create_electronic_invoice = False
                    if sale.receipt.voucher_type == VOUCHER_TYPE[0][0]:
                        sale.time_limit = int(request.POST['time_limit'])
                        sale.payment_method = request.POST['payment_method']
                        sale.create_electronic_invoice = 'create_electronic_invoice' in request.POST
                        sale.observations = request.POST.get('observations', '')
                    if sale.payment_type == 'efectivo':
                        sale.cash = float(request.POST['cash'])
                        sale.change = float(request.POST['change'])
                    elif sale.payment_type == 'credito':
                        sale.end_credit = request.POST['end_credit']
                        sale.cash = 0.00
                        sale.change = 0.00
                    elif sale.payment_type == 'transferencia':
                        sale.transfer_bank = request.POST.get('transfer_bank')
                        sale.transfer_number = request.POST.get('transfer_number')
                        sale.cash = 0.00
                        sale.change = 0.00
                    elif sale.payment_type == 'tarjeta_credito':
                        sale.card_type = request.POST.get('card_type')
                        sale.card_transaction_type = request.POST.get('card_transaction_type')
                        sale.card_owner_id = request.POST.get('card_owner_id')
                        sale.card_authorization_number = request.POST.get('card_authorization_number')
                        sale.cash = 0.00
                        sale.change = 0.00
                    sale.save()
                    customer_type = sale.client.customer_type
                    for i in json.loads(request.POST['products']):
                        product = Product.objects.get(pk=i['id'])
                        cant = int(i['cant'])
                        if cant <= 0:
                            raise ValueError(f'Cantidad inválida para {product.name}')
                        if product.inventoried and product.stock < cant:
                            raise ValueError(f'Stock insuficiente para {product.name} (disponible: {product.stock})')
                        # El precio se recalcula en el servidor a partir del tipo de
                        # cliente y las promociones vigentes -nunca se confía en el
                        # "price_current" que manda el navegador, que podría venir
                        # alterado-. El descuento sí lo puede elegir el vendedor,
                        # pero se acota a un rango válido de 0% a 100%.
                        price = product.get_price_current(customer_type)
                        dscto = max(0.0, min(float(i.get('dscto', 0)), 100.0)) / 100
                        detail = SaleDetail.objects.create(
                            sale_id=sale.id,
                            product_id=product.id,
                            cant=cant,
                            price=price,
                            dscto=dscto
                        )
                        if detail.product.inventoried:
                            detail.product.register_movement(-detail.cant, 'venta', f'Venta {sale.voucher_number_full}', user=request.user)
                    sale.calculate_detail()
                    sale.calculate_invoice()
                    if sale.payment_type == 'credito':
                        ctas_collect = CtasCollect()
                        ctas_collect.sale_id = sale.id
                        ctas_collect.date_joined = sale.date_joined
                        ctas_collect.end_date = sale.end_credit
                        ctas_collect.debt = sale.total
                        ctas_collect.saldo = sale.total
                        ctas_collect.save()
                    data = {'print_url': str(reverse_lazy('sale_admin_print_invoice', kwargs={'pk': sale.id}))}
                    if sale.create_electronic_invoice:
                        data = sale.generate_electronic_invoice()
                        if not data['resp']:
                            transaction.set_rollback(True)
                if 'error' in data:
                    SRI().create_voucher_errors(sale, data)
            elif action == 'search_product':
                customer_type = request.POST.get('customer_type', CUSTOMER_TYPE[0][0])
                ids = json.loads(request.POST['ids'])
                data = []
                term = request.POST['term']
                queryset = Product.objects.filter(Q(stock__gt=0) | Q(inventoried=False)).exclude(id__in=ids).order_by('name')
                if len(term):
                    queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
                    queryset = queryset[:10]
                for i in queryset:
                    # No se envía el precio de costo (price) al vendedor: solo
                    # necesita los precios de venta, y ese dato era visible en
                    # la pestaña de red del navegador para cualquier cajero.
                    item = i.toJSON(exclude=['price'])
                    item['price_current'] = i.get_price_current(customer_type)
                    item['pvp'] = float(i.pvp)
                    item['value'] = i.get_full_name()
                    item['dscto'] = 0.00
                    item['total_dscto'] = 0.00
                    data.append(item)
            elif action == 'search_product_code':
                data = {}
                customer_type = request.POST.get('customer_type', CUSTOMER_TYPE[0][0])
                code = request.POST['code']
                if len(code):
                    product = Product.objects.filter(code=code).first()
                    if product:
                        data = product.toJSON(exclude=['price'])
                        data['price_current'] = product.get_price_current(customer_type)
                        data['dscto'] = 0.00
                        data['total_dscto'] = 0.00
            elif action == 'search_client':
                data = []
                term = request.POST['term']
                for i in Client.objects.filter(Q(user__names__icontains=term) | Q(dni__icontains=term)).order_by('user__names')[0:10]:
                    data.append(i.toJSON())
            elif action == 'search_voucher_number':
                data['voucher_number'] = ''
                receipt = Receipt.objects.filter(voucher_type=request.POST['receipt'], establishment_code=request.tenant.company.establishment_code, issuing_point_code=request.tenant.company.issuing_point_code).first()
                if receipt:
                    data['voucher_number'] = f'{receipt.sequence + 1:09d}'
            elif action == 'validate_client':
                data = {'valid': True}
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                queryset = Client.objects.all()
                if pattern == 'dni':
                    data['valid'] = not queryset.filter(dni=parameter).exists()
                elif pattern == 'mobile':
                    data['valid'] = not queryset.filter(mobile=parameter).exists()
                elif pattern == 'email':
                    data['valid'] = not queryset.filter(user__email=parameter).exists()
            elif action == 'create_client':
                with transaction.atomic():
                    form1 = ClientUserForm(self.request.POST, self.request.FILES)
                    form2 = ClientForm(request.POST)
                    if form1.is_valid() and form2.is_valid():
                        user = form1.save(commit=False)
                        user.username = form2.cleaned_data['dni']
                        user.set_password(user.username)
                        user.save()
                        user.groups.add(Group.objects.get(pk=settings.GROUPS['client']))
                        form_client = form2.save(commit=False)
                        form_client.user = user
                        form_client.save()
                        data = Client.objects.get(pk=form_client.id).toJSON()
                    else:
                        if not form1.is_valid():
                            data['error'] = form1.errors
                        elif not form2.is_valid():
                            data['error'] = form2.errors
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de una Venta'
        context['frmClient'] = ClientForm()
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['frmUser'] = ClientUserForm()
        context['final_consumer'] = json.dumps(self.get_first_final_consumer())
        return context


class SaleDeleteView(GroupPermissionMixin, DeleteView):
    model = Sale
    template_name = 'delete.html'
    success_url = reverse_lazy('sale_admin_list')
    permission_required = 'delete_sale'

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


class SalePrintInvoiceView(LoginRequiredMixin, View):
    success_url = reverse_lazy('sale_admin_list')

    def get_success_url(self):
        if self.request.user.is_client():
            return reverse_lazy('sale_client_list')
        return self.success_url

    def get(self, request, *args, **kwargs):
        try:
            sale = Sale.objects.filter(id=self.kwargs['pk']).first()
            if sale:
                context = {'sale': sale, 'height': 650 + sale.saledetail_set.all().count() * 18, 'client_qr': self.get_client_qr(sale)}
                pdf_file = printer.create_pdf(context=context, template_name='sale/format/ticket.html')
                return HttpResponse(pdf_file, content_type='application/pdf')
            messages.error(request, 'La venta no existe')
        except Exception as e:
            messages.error(request, str(e))
        return HttpResponseRedirect(self.get_success_url())

    def get_client_qr(self, sale):
        if not sale.company.website:
            return None
        url = f"{sale.company.website.rstrip('/')}/login/?next=/pos/sale/client/"
        qr_image = qrcode.make(url, border=1)
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        return f'data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode("ascii")}'


class SaleClientListView(GroupPermissionMixin, FormView):
    template_name = 'sale/client/list.html'
    form_class = ReportForm
    permission_required = 'view_sale_client'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = Sale.objects.filter(client__user_id=request.user.id)
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_detail_products':
                data = []
                for i in SaleDetail.objects.filter(sale_id=request.POST['id']):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Ventas'
        return context

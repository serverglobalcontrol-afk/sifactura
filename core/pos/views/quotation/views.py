import json

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.pos.choices import CUSTOMER_TYPE, VOUCHER_TYPE
from core.pos.forms import QuotationForm, Quotation, Client, Product, QuotationDetail, Receipt
from core.pos.utilities.pdf_creator import PDFCreator
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class QuotationListView(GroupPermissionMixin, ListView):
    model = Quotation
    template_name = 'quotation/list.html'
    permission_required = 'view_quotation'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                filters = Q()
                if len(start_date) and len(end_date):
                    filters &= Q(date_joined__range=[start_date, end_date])
                for i in self.model.objects.filter(filters):
                    item = i.toJSON()
                    item['validate_stock'] = i.validate_stock
                    data.append(item)
            elif action == 'search_detail_products':
                data = []
                for i in QuotationDetail.objects.filter(quotation_id=request.POST['id']):
                    item = i.toJSON()
                    item['validate_stock'] = i.product.stock >= i.cant if i.product.inventoried else True
                    data.append(item)
            elif action == 'send_quotation_by_email':
                quotation = Quotation.objects.get(id=request.POST['id'])
                quotation.send_quotation_by_email()
            elif action == 'create_electronic_invoice':
                quotation = Quotation.objects.get(id=request.POST['id'])
                data = quotation.create_invoice(observations=request.POST.get('observations', ''))
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Listado de {self.model._meta.verbose_name_plural}'
        context['create_url'] = reverse_lazy('quotation_create')
        context['form'] = ReportForm()
        return context


class QuotationCreateView(GroupPermissionMixin, CreateView):
    model = Quotation
    template_name = 'quotation/create.html'
    form_class = QuotationForm
    success_url = reverse_lazy('quotation_list')
    permission_required = 'add_quotation'

    def get_end_consumer(self):
        client = Client.objects.filter(dni='9999999999999').first()
        return client.toJSON() if client else dict()

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                with transaction.atomic():
                    quotation = Quotation()
                    quotation.client_id = int(request.POST['client'])
                    quotation.company = request.tenant.company
                    quotation.employee_id = request.user.id
                    quotation.date_joined = request.POST['date_joined']
                    quotation.validity_days = int(request.POST['validity_days'])
                    quotation.observations = request.POST.get('observations', '')
                    quotation.iva = quotation.company.tax_rate
                    quotation.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[3][0], establishment_code=quotation.company.establishment_code, issuing_point_code=quotation.company.issuing_point_code)
                    quotation.voucher_number = quotation.generate_voucher_number()
                    quotation.voucher_number_full = quotation.get_voucher_number_full()
                    quotation.save()
                    for i in json.loads(request.POST['products']):
                        product = Product.objects.get(pk=i['id'])
                        QuotationDetail.objects.create(
                            quotation_id=quotation.id,
                            product_id=product.id,
                            cant=int(i['cant']),
                            price=float(i['price_current']),
                            dscto=float(i['dscto']) / 100
                        )
                    quotation.recalculate_invoice()
                    data = {'print_url': str(reverse_lazy('quotation_print', kwargs={'pk': quotation.id}))}
            elif action == 'search_product':
                customer_type = request.POST.get('customer_type', CUSTOMER_TYPE[0][0])
                product_id = json.loads(request.POST['product_id'])
                data = []
                term = request.POST['term']
                filters = Q()
                if len(term):
                    filters &= Q(Q(name__icontains=term) | Q(code__icontains=term))
                queryset = Product.objects.filter(filters).exclude(id__in=product_id).order_by('name')
                if not filters.children:
                    queryset = queryset[0:10]
                for i in queryset:
                    item = i.toJSON()
                    item['price_current'] = i.get_price_current(customer_type)
                    # Se agrega el stock (o "Sin inventario" si el producto no
                    # se inventaría, ej. servicios) al texto que ve el usuario
                    # en el autocompletado de búsqueda de productos.
                    stock_label = f'Stock: {i.stock}' if i.inventoried else 'Sin inventario'
                    item['value'] = f'{i.get_full_name()} — {stock_label}'
                    item['dscto'] = 0.00
                    item['total_dscto'] = 0.00
                    data.append(item)
            elif action == 'search_product_code':
                code = request.POST['code']
                customer_type = request.POST.get('customer_type', CUSTOMER_TYPE[0][0])
                if len(code):
                    product = Product.objects.filter(code=code).first()
                    if product:
                        data = product.toJSON()
                        data['price_current'] = product.get_price_current(customer_type)
                        data['dscto'] = 0.00
                        data['total_dscto'] = 0.00
            elif action == 'search_client':
                data = []
                term = request.POST['term']
                for i in Client.objects.filter(Q(user__names__icontains=term) | Q(dni__icontains=term)).order_by('user__names')[0:10]:
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = f'Creación de una {self.model._meta.verbose_name}'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['end_consumer'] = json.dumps(self.get_end_consumer())
        context['products'] = []
        return context


class QuotationUpdateView(GroupPermissionMixin, UpdateView):
    model = Quotation
    template_name = 'quotation/create.html'
    form_class = QuotationForm
    success_url = reverse_lazy('quotation_list')
    permission_required = 'change_quotation'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                with transaction.atomic():
                    quotation = self.get_object()
                    quotation.client_id = int(request.POST['client'])
                    quotation.employee_id = request.user.id
                    quotation.company = request.tenant.company
                    quotation.date_joined = request.POST['date_joined']
                    quotation.validity_days = int(request.POST['validity_days'])
                    quotation.observations = request.POST.get('observations', '')
                    quotation.iva = quotation.company.tax_rate
                    quotation.save()
                    quotation.quotationdetail_set.all().delete()
                    for i in json.loads(request.POST['products']):
                        product = Product.objects.get(pk=i['id'])
                        QuotationDetail.objects.create(
                            quotation_id=quotation.id,
                            product_id=product.id,
                            cant=int(i['cant']),
                            price=float(i['price_current']),
                            dscto=float(i['dscto']) / 100
                        )
                    quotation.recalculate_invoice()
                    data = {'print_url': str(reverse_lazy('quotation_print', kwargs={'pk': quotation.id}))}
            elif action == 'search_product':
                customer_type = request.POST.get('customer_type', CUSTOMER_TYPE[0][0])
                product_id = json.loads(request.POST['product_id'])
                data = []
                term = request.POST['term']
                filters = Q()
                if len(term):
                    filters &= Q(Q(name__icontains=term) | Q(code__icontains=term))
                queryset = Product.objects.filter(filters).exclude(id__in=product_id).order_by('name')
                if not filters.children:
                    queryset = queryset[0:10]
                for i in queryset:
                    item = i.toJSON()
                    item['price_current'] = i.get_price_current(customer_type)
                    # Se agrega el stock (o "Sin inventario" si el producto no
                    # se inventaría, ej. servicios) al texto que ve el usuario
                    # en el autocompletado de búsqueda de productos.
                    stock_label = f'Stock: {i.stock}' if i.inventoried else 'Sin inventario'
                    item['value'] = f'{i.get_full_name()} — {stock_label}'
                    item['dscto'] = 0.00
                    item['total_dscto'] = 0.00
                    data.append(item)
            elif action == 'search_product_code':
                code = request.POST['code']
                customer_type = request.POST.get('customer_type', CUSTOMER_TYPE[0][0])
                if len(code):
                    product = Product.objects.filter(code=code).first()
                    if product:
                        data = product.toJSON()
                        data['price_current'] = product.get_price_current(customer_type)
                        data['dscto'] = 0.00
                        data['total_dscto'] = 0.00
            elif action == 'search_client':
                data = []
                term = request.POST['term']
                for i in Client.objects.filter(Q(user__names__icontains=term) | Q(dni__icontains=term)).order_by('user__names')[0:10]:
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_products(self):
        data = []
        for detail in self.object.quotationdetail_set.all():
            item = detail.product.toJSON()
            item['cant'] = detail.cant
            item['price_current'] = float(detail.price)
            item['dscto'] = float(detail.dscto * 100)
            item['total_dscto'] = float(detail.total_dscto)
            data.append(item)
        return json.dumps(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = f'Edición de una {self.model._meta.verbose_name}'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        context['end_consumer'] = json.dumps(self.object.client.toJSON())
        context['products'] = self.get_products()
        return context


class QuotationDeleteView(GroupPermissionMixin, DeleteView):
    model = Quotation
    template_name = 'delete.html'
    success_url = reverse_lazy('quotation_list')
    permission_required = 'delete_quotation'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Eliminación de una {self.model._meta.verbose_name}'
        context['list_url'] = self.success_url
        return context


class QuotationPrintView(GroupPermissionMixin, ListView):
    model = Quotation
    template_name = 'quotation/invoice_pdf.html'
    success_url = reverse_lazy('quotation_list')
    permission_required = 'print_quotation'

    def get(self, request, *args, **kwargs):
        quotation = self.model.objects.filter(id=self.kwargs['pk']).first()
        if quotation:
            context = {'quotation': quotation}
            pdf_file = PDFCreator(template_name=self.template_name).create(context=context)
            response = HttpResponse(pdf_file, content_type='application/pdf')
            client_name = quotation.client.user.names.strip().replace(' ', '_')
            filename = f"Cotizacion_{quotation.date_joined.strftime('%Y%m%d')}_{quotation.formatted_number}_{client_name}.pdf"
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response
        return HttpResponseRedirect(self.success_url)

import json
from datetime import datetime
from io import BytesIO

import pandas as pd
import xlsxwriter
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, TemplateView
from django.views.generic.base import View
from openpyxl import load_workbook

from core.pos.forms import ProductForm, Product, Category
from core.security.mixins import GroupPermissionMixin


class ProductListView(GroupPermissionMixin, TemplateView):
    template_name = 'product/list.html'
    permission_required = 'view_product'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Product.objects.filter():
                    data.append(i.toJSON())
            elif action == 'upload_excel':
                with transaction.atomic():
                    archive = request.FILES['archive']

                    df = pd.read_excel(
                        archive,
                        engine='openpyxl',
                        dtype={
                            'Código': str,
                            '¿Es inventariado?': str,
                            '¿Se cobra impuesto?': str
                        }
                    )

                    df = df.fillna('')

                    codes = df['Código'].astype(str).tolist()

                    existing_products = {
                        p.code: p for p in Product.objects.filter(code__in=codes)
                    }

                    category_names = df['Categoría'].unique().tolist()
                    existing_categories = {
                        c.name: c for c in Category.objects.filter(name__in=category_names)
                    }

                    products_to_create = []
                    products_to_update = []

                    for _, record in df.iterrows():
                        code = str(record['Código']).strip()
                        product = existing_products.get(code)

                        category_name = str(record['Categoría']).strip()

                        category = existing_categories.get(category_name)
                        if not category:
                            category = Category.objects.create(name=category_name)
                            existing_categories[category_name] = category

                        is_new = product is None

                        if is_new:
                            product = Product(code=code)

                        product.name = record['Nombre']
                        product.category = category
                        product.price = float(record['Precio de Compra'] or 0)
                        product.pvp = float(record['Precio de Venta'] or 0)
                        product.wholesale_price = float(record['Precio distribuidor'] or 0)
                        product.credit_card_price = float(record['Precio tarjeta de crédito'] or 0)
                        product.stock = int(record['Stock'] or 0)
                        product.inventoried = str(record['¿Es inventariado?']).lower() == 'si'
                        product.with_tax = str(record['¿Se cobra impuesto?']).lower() == 'si'

                        if is_new:
                            products_to_create.append(product)
                        else:
                            products_to_update.append(product)

                    if products_to_create:
                        Product.objects.bulk_create(products_to_create, batch_size=1000)

                    if products_to_update:
                        Product.objects.bulk_update(
                            products_to_update,
                            [
                                'name',
                                'category',
                                'price',
                                'pvp',
                                'wholesale_price',
                                'credit_card_price',
                                'stock',
                                'inventoried',
                                'with_tax'
                            ],
                            batch_size=1000
                        )
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Productos'
        context['create_url'] = reverse_lazy('product_create')
        return context


class ProductCreateView(GroupPermissionMixin, CreateView):
    model = Product
    template_name = 'product/create.html'
    form_class = ProductForm
    success_url = reverse_lazy('product_list')
    permission_required = 'add_product'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            elif action == 'validate_data':
                data = {'valid': True}
                queryset = Product.objects.all()
                pattern = request.POST['pattern']
                if pattern == 'name':
                    name = request.POST['name'].strip()
                    category = request.POST['category']
                    if len(category):
                        data['valid'] = not queryset.filter(name__iexact=name, category_id=category).exists()
                elif pattern == 'code':
                    data['valid'] = not queryset.filter(code__iexact=request.POST['code']).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Producto'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class ProductUpdateView(GroupPermissionMixin, UpdateView):
    model = Product
    template_name = 'product/create.html'
    form_class = ProductForm
    success_url = reverse_lazy('product_list')
    permission_required = 'change_product'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                data = self.get_form().save()
            elif action == 'validate_data':
                data = {'valid': True}
                id = self.get_object().id
                queryset = Product.objects.all().exclude(id=id)
                pattern = request.POST['pattern']
                if pattern == 'name':
                    name = request.POST['name'].strip()
                    category = request.POST['category']
                    if len(category):
                        data['valid'] = not queryset.filter(name__iexact=name, category_id=category).exists()
                elif pattern == 'code':
                    data['valid'] = not queryset.filter(code__iexact=request.POST['code']).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de un Producto'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class ProductDeleteView(GroupPermissionMixin, DeleteView):
    model = Product
    template_name = 'delete.html'
    success_url = reverse_lazy('product_list')
    permission_required = 'delete_product'

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


class ProductStockAdjustmentView(GroupPermissionMixin, TemplateView):
    template_name = 'product/stock_adjustment.html'
    permission_required = 'adjust_product_stock'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search_product':
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
            elif action == 'create':
                with transaction.atomic():
                    for i in json.loads(request.POST['products']):
                        product = Product.objects.get(pk=i['id'])
                        product.stock = int(i['newstock'])
                        product.save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Ajuste de Stock de Productos'
        return context


class ProductExportExcelView(GroupPermissionMixin, View):
    # Antes solo pedía sesión iniciada (LoginRequiredMixin): cualquier usuario
    # logueado, sin importar su rol, podía descargar el catálogo completo de
    # productos (incluye costo y stock). Se exige el mismo permiso que ya
    # protege el listado.
    permission_required = 'view_product'

    def get(self, request, *args, **kwargs):
        try:
            headers = {
                'Id': 15, 'Nombre': 75, 'Código': 20, 'Categoría': 20, 'Precio de Compra': 20,
                'Precio de Venta': 20,
                'Precio distribuidor': 20,
                'Precio tarjeta de crédito': 20,
                'Stock': 10,
                '¿Es inventariado?': 15,
                '¿Se cobra impuesto?': 15}
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('productos')
            cell_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
            row_format = workbook.add_format({'align': 'center', 'border': 1})
            index = 0
            for name, width in headers.items():
                worksheet.set_column(first_col=index, last_col=index, width=width)
                worksheet.write(0, index, name, cell_format)
                index += 1
            row = 1
            for product in Product.objects.filter().order_by('id'):
                worksheet.write(row, 0, product.id, row_format)
                worksheet.write(row, 1, product.name, row_format)
                worksheet.write(row, 2, product.code, row_format)
                worksheet.write(row, 3, product.category.name, row_format)
                worksheet.write(row, 4, f'{product.price:.2f}', row_format)
                worksheet.write(row, 5, f'{product.pvp:.2f}', row_format)
                worksheet.write(row, 6, f'{product.wholesale_price:.2f}', row_format)
                worksheet.write(row, 7, f'{product.credit_card_price:.2f}', row_format)
                worksheet.write(row, 8, product.stock, row_format)
                worksheet.write(row, 9, 'Si' if product.inventoried else 'No', row_format)
                worksheet.write(row, 10, 'Si' if product.with_tax else 'No', row_format)
                row += 1
            workbook.close()
            output.seek(0)
            response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f"attachment; filename=PRODUCTOS_{datetime.now().date().strftime('%d_%m_%Y')}.xlsx"
            return response
        except:
            pass
        return HttpResponseRedirect(reverse_lazy('product_list'))

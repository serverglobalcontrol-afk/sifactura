import json
from datetime import datetime
from io import BytesIO

import pandas as pd
import xlsxwriter
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView
from django.views.generic.base import View

from core.pos.forms import Category, CategoryForm
from core.security.mixins import GroupPermissionMixin


class CategoryListView(GroupPermissionMixin, TemplateView):
    template_name = 'category/list.html'
    permission_required = 'view_category'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Category.objects.all():
                    data.append(i.toJSON())
            elif action == 'upload_excel':
                with transaction.atomic():
                    archive = request.FILES['archive']

                    df = pd.read_excel(archive, engine='openpyxl', dtype={'Nombre': str})
                    df = df.fillna('')

                    names = [str(n).strip() for n in df['Nombre'].tolist() if str(n).strip()]
                    existing_names = set(Category.objects.filter(name__in=names).values_list('name', flat=True))

                    categories_to_create = [
                        Category(name=name)
                        for name in dict.fromkeys(names)
                        if name not in existing_names
                    ]

                    if categories_to_create:
                        Category.objects.bulk_create(categories_to_create, batch_size=1000)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Categorías'
        context['create_url'] = reverse_lazy('category_create')
        return context


class CategoryCreateView(GroupPermissionMixin, CreateView):
    model = Category
    template_name = 'category/create.html'
    form_class = CategoryForm
    success_url = reverse_lazy('category_list')
    permission_required = 'add_category'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            elif action == 'validate_data':
                data = {'valid': True}
                queryset = Category.objects.all()
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                if pattern == 'name':
                    data['valid'] = not queryset.filter(name__iexact=parameter).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de una Categoría'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class CategoryUpdateView(GroupPermissionMixin, UpdateView):
    model = Category
    template_name = 'category/create.html'
    form_class = CategoryForm
    success_url = reverse_lazy('category_list')
    permission_required = 'change_category'

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
                queryset = Category.objects.all().exclude(id=self.object.id)
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                if pattern == 'name':
                    data['valid'] = not queryset.filter(name__iexact=parameter).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de una Categoría'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class CategoryDeleteView(GroupPermissionMixin, DeleteView):
    model = Category
    template_name = 'delete.html'
    success_url = reverse_lazy('category_list')
    permission_required = 'delete_category'

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


class CategoryExportExcelView(GroupPermissionMixin, View):
    permission_required = 'view_category'

    def get(self, request, *args, **kwargs):
        try:
            headers = {'Id': 15, 'Nombre': 60}
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('categorias')
            cell_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
            row_format = workbook.add_format({'align': 'center', 'border': 1})
            index = 0
            for name, width in headers.items():
                worksheet.set_column(first_col=index, last_col=index, width=width)
                worksheet.write(0, index, name, cell_format)
                index += 1
            row = 1
            for category in Category.objects.all().order_by('id'):
                worksheet.write(row, 0, category.id, row_format)
                worksheet.write(row, 1, category.name, row_format)
                row += 1
            workbook.close()
            output.seek(0)
            response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f"attachment; filename=CATEGORIAS_{datetime.now().date().strftime('%d_%m_%Y')}.xlsx"
            return response
        except Exception as e:
            messages.error(request, str(e))
        return HttpResponseRedirect(reverse_lazy('category_list'))

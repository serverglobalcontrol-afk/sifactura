import json
from datetime import datetime
from io import BytesIO

import xlsxwriter
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView
from django.views.generic.base import View

from core.pos.forms import Provider, ProviderForm
from core.pos.utilities.sri import SRI
from core.security.mixins import GroupPermissionMixin


class ProviderListView(GroupPermissionMixin, TemplateView):
    template_name = 'provider/list.html'
    permission_required = 'view_provider'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Provider.objects.all():
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Proveedores'
        context['create_url'] = reverse_lazy('provider_create')
        return context


class ProviderCreateView(GroupPermissionMixin, CreateView):
    model = Provider
    template_name = 'provider/create.html'
    form_class = ProviderForm
    success_url = reverse_lazy('provider_list')
    permission_required = 'add_provider'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            elif action == 'validate_data':
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
            elif action == 'search_ruc_in_sri':
                data = SRI().search_ruc_in_sri(ruc=request.POST['ruc'])
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Proveedor'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class ProviderUpdateView(GroupPermissionMixin, UpdateView):
    model = Provider
    template_name = 'provider/create.html'
    form_class = ProviderForm
    success_url = reverse_lazy('provider_list')
    permission_required = 'change_provider'

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
                queryset = Provider.objects.all().exclude(id=self.object.id)
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
            elif action == 'search_ruc_in_sri':
                data = SRI().search_ruc_in_sri(ruc=request.POST['ruc'])
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de un Proveedor'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class ProviderDeleteView(GroupPermissionMixin, DeleteView):
    model = Provider
    template_name = 'delete.html'
    success_url = reverse_lazy('provider_list')
    permission_required = 'delete_provider'

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


class ProviderExportExcelView(GroupPermissionMixin, View):
    permission_required = 'view_provider'

    def get(self, request, *args, **kwargs):
        try:
            headers = {'Id': 15, 'Razón Social': 50, 'RUC': 20, 'Teléfono celular': 20, 'Email': 35, 'Dirección': 50}
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('proveedores')
            cell_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
            row_format = workbook.add_format({'align': 'center', 'border': 1})
            index = 0
            for name, width in headers.items():
                worksheet.set_column(first_col=index, last_col=index, width=width)
                worksheet.write(0, index, name, cell_format)
                index += 1
            row = 1
            for provider in Provider.objects.all().order_by('id'):
                worksheet.write(row, 0, provider.id, row_format)
                worksheet.write(row, 1, provider.name, row_format)
                worksheet.write(row, 2, provider.ruc, row_format)
                worksheet.write(row, 3, provider.mobile, row_format)
                worksheet.write(row, 4, provider.email, row_format)
                worksheet.write(row, 5, provider.address or '', row_format)
                row += 1
            workbook.close()
            output.seek(0)
            response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f"attachment; filename=PROVEEDORES_{datetime.now().date().strftime('%d_%m_%Y')}.xlsx"
            return response
        except Exception as e:
            messages.error(request, str(e))
        return HttpResponseRedirect(reverse_lazy('provider_list'))

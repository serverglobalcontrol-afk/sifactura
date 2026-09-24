import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView

from core.pos.forms import TypeIncome, TypeIncomeForm
from core.security.mixins import GroupPermissionMixin


class TypeIncomeListView(GroupPermissionMixin, TemplateView):
    template_name = 'type_income/list.html'
    permission_required = 'view_type_income'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in TypeIncome.objects.all():
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['create_url'] = reverse_lazy('type_income_create')
        context['title'] = 'Listado de Tipos de Ingresos'
        return context


class TypeIncomeCreateView(GroupPermissionMixin, CreateView):
    model = TypeIncome
    template_name = 'type_income/create.html'
    form_class = TypeIncomeForm
    success_url = reverse_lazy('type_income_list')
    permission_required = 'add_type_income'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            elif action == 'validate_data':
                data = {'valid': True}
                queryset = TypeIncome.objects.all()
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
        context['list_url'] = self.success_url
        context['title'] = 'Nuevo registro de un Tipo de Ingreso'
        context['action'] = 'add'
        return context


class TypeIncomeUpdateView(GroupPermissionMixin, UpdateView):
    model = TypeIncome
    template_name = 'type_income/create.html'
    form_class = TypeIncomeForm
    success_url = reverse_lazy('type_income_list')
    permission_required = 'change_type_income'

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
                queryset = TypeIncome.objects.all().exclude(id=self.object.id)
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
        context['list_url'] = self.success_url
        context['title'] = 'Edición de un Tipo de Ingreso'
        context['action'] = 'edit'
        return context


class TypeIncomeDeleteView(GroupPermissionMixin, DeleteView):
    model = TypeIncome
    template_name = 'delete.html'
    success_url = reverse_lazy('type_income_list')
    permission_required = 'delete_type_income'

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

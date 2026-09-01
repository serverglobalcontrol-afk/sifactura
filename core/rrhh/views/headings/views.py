import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView

from core.rrhh.forms import HeadingsForm, Headings
from core.security.mixins import GroupPermissionMixin


class HeadingsListView(GroupPermissionMixin, TemplateView):
    template_name = 'headings/list.html'
    permission_required = 'view_headings'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Headings.objects.all().order_by('type', 'order'):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Rubros'
        context['create_url'] = reverse_lazy('headings_create')
        return context


class HeadingsCreateView(GroupPermissionMixin, CreateView):
    model = Headings
    template_name = 'headings/create.html'
    form_class = HeadingsForm
    success_url = reverse_lazy('headings_list')
    permission_required = 'add_headings'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            elif action == 'validate_data':
                data = {'valid': True}
                queryset = Headings.objects.all()
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                if pattern == 'name':
                    data['valid'] = not queryset.filter(name__iexact=parameter).exists()
                elif pattern == 'code':
                    data['valid'] = not queryset.filter(code__iexact=parameter).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Rubro'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class HeadingsUpdateView(GroupPermissionMixin, UpdateView):
    model = Headings
    template_name = 'headings/create.html'
    form_class = HeadingsForm
    success_url = reverse_lazy('headings_list')
    permission_required = 'change_headings'

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
                queryset = Headings.objects.all().exclude(id=self.object.id)
                pattern = request.POST['pattern']
                parameter = request.POST['parameter'].strip()
                if pattern == 'name':
                    data['valid'] = not queryset.filter(name__iexact=parameter).exists()
                elif pattern == 'code':
                    data['valid'] = not queryset.filter(code__iexact=parameter).exists()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de un Rubro'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class HeadingsDeleteView(GroupPermissionMixin, DeleteView):
    model = Headings
    template_name = 'headings/delete.html'
    success_url = reverse_lazy('headings_list')
    permission_required = 'delete_headings'

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

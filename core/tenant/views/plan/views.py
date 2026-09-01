import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView

from core.tenant.forms import Plan, PlanForm
from core.security.mixins import GroupPermissionMixin


class PlanListView(GroupPermissionMixin, TemplateView):
    template_name = 'plan/list.html'
    permission_required = 'view_plan'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Plan.objects.all():
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Planes'
        context['create_url'] = reverse_lazy('plan_create')
        return context


class PlanCreateView(GroupPermissionMixin, CreateView):
    model = Plan
    template_name = 'plan/create.html'
    form_class = PlanForm
    success_url = reverse_lazy('plan_list')
    permission_required = 'add_plan'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            elif action == 'validate_data':
                data = {'valid': True}
                queryset = Plan.objects.all()
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
        context['title'] = 'Nuevo registro de un Plan'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class PlanUpdateView(GroupPermissionMixin, UpdateView):
    model = Plan
    template_name = 'plan/create.html'
    form_class = PlanForm
    success_url = reverse_lazy('plan_list')
    permission_required = 'change_plan'

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
                queryset = Plan.objects.all().exclude(id=self.object.id)
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
        context['title'] = 'Edición de un Plan'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class PlanDeleteView(GroupPermissionMixin, DeleteView):
    model = Plan
    template_name = 'delete.html'
    success_url = reverse_lazy('plan_list')
    permission_required = 'delete_plan'

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

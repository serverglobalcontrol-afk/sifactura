import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView, UpdateView, DeleteView

from core.marketing.forms import Promotion, PromotionForm
from core.security.mixins import GroupPermissionMixin


class PromotionListView(GroupPermissionMixin, TemplateView):
    template_name = 'promotion/list.html'
    permission_required = 'view_promotion'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Promotion.objects.all():
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Promociones'
        context['create_url'] = reverse_lazy('promotion_create')
        return context


class PromotionCreateView(GroupPermissionMixin, CreateView):
    model = Promotion
    template_name = 'promotion/create.html'
    form_class = PromotionForm
    success_url = reverse_lazy('promotion_list')
    permission_required = 'add_promotion'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nueva Promoción'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class PromotionUpdateView(GroupPermissionMixin, UpdateView):
    model = Promotion
    template_name = 'promotion/create.html'
    form_class = PromotionForm
    success_url = reverse_lazy('promotion_list')
    permission_required = 'change_promotion'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de Promoción'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class PromotionDeleteView(GroupPermissionMixin, DeleteView):
    model = Promotion
    template_name = 'delete.html'
    success_url = reverse_lazy('promotion_list')
    permission_required = 'delete_promotion'

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

import json

from django import forms
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import FormView

from core.pos.models import PriceType, PRICE_TYPE_ORDER
from core.security.mixins import GroupPermissionMixin

TYPE_LABELS = {
    'wholesale': 'Nombre para el precio Distribuidor',
    'retail': 'Nombre para el precio Público',
    'credit_card': 'Nombre para el precio Tarjeta de Crédito',
}


class PriceTypeForm(forms.Form):
    wholesale = forms.CharField(max_length=50, label=TYPE_LABELS['wholesale'])
    retail = forms.CharField(max_length=50, label=TYPE_LABELS['retail'])
    credit_card = forms.CharField(max_length=50, label=TYPE_LABELS['credit_card'])


class PriceTypeUpdateView(GroupPermissionMixin, FormView):
    template_name = 'price_type/edit.html'
    form_class = PriceTypeForm
    success_url = reverse_lazy('price_type_update')
    permission_required = 'change_price_type'

    def get_initial(self):
        return PriceType.get_labels()

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST.get('action')
        try:
            if action == 'edit':
                form = self.get_form()
                if form.is_valid():
                    for code in PRICE_TYPE_ORDER:
                        PriceType.objects.update_or_create(code=code, defaults={'name': form.cleaned_data[code]})
                else:
                    data['error'] = form.errors
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Tipos de Precio'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context

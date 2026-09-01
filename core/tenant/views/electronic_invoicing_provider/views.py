import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from config import settings
from core.security.mixins import GroupPermissionMixin
from core.tenant.forms import ElectronicInvoicingProvider, ElectronicInvoicingProviderForm


class ElectronicInvoicingProviderUpdateView(GroupPermissionMixin, UpdateView):
    template_name = 'electronic_invoicing_provider/create.html'
    form_class = ElectronicInvoicingProviderForm
    model = ElectronicInvoicingProvider
    permission_required = 'change_electronicinvoicingprovider'
    success_url = settings.LOGIN_REDIRECT_URL

    def get_object(self, queryset=None):
        provider = ElectronicInvoicingProvider.objects.first()
        if provider:
            return provider
        return ElectronicInvoicingProvider()

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        instance = self.get_object()
        if instance.pk is not None:
            form.instance = instance
        return form

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
        context['title'] = 'Proveedor de Facturación Electrónica'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context

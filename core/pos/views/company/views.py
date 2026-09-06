import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from django.http import HttpResponse
from django.views.generic import UpdateView

from config import settings
from core.security.mixins import GroupPermissionMixin
from core.tenant.forms import CompanyForm, Company, COMPANY_FIELD_GROUPS, build_field_groups

EDITABLE_FIELDS = [
    'image', 'electronic_signature', 'electronic_signature_key',
    'email_host', 'email_port', 'email_host_user', 'email_host_password',
    'enable_ticket_sale', 'enable_purchase_settlement',
    'backup_schedule_enabled', 'backup_schedule_frequency', 'backup_schedule_weekday', 'backup_schedule_time',
]


class CompanyUpdateView(GroupPermissionMixin, UpdateView):
    template_name = 'company/edit.html'
    form_class = CompanyForm
    model = Company
    permission_required = 'change_company'
    success_url = settings.LOGIN_REDIRECT_URL

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields['active']
        for field in Company._meta.fields:
            if field.name in form.fields and field.name not in EDITABLE_FIELDS:
                form.fields[field.name].widget.attrs['disabled'] = True
        return form

    def get_object(self, queryset=None):
        return self.request.tenant.company

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                instance = self.get_object()
                form = self.get_form()
                form.data._mutable = True
                for field in Company._meta.fields:
                    if field.name in form.fields and field.name not in EDITABLE_FIELDS:
                        form.data[field.name] = getattr(instance, field.name)
                data = form.save()
            elif action == 'reveal_secrets':
                instance = self.get_object()
                data = {
                    'electronic_signature_key': instance.electronic_signature_key,
                    'email_host_password': instance.email_host_password,
                }
            elif action == 'load_certificate':
                instance = self.get_object()
                electronic_signature_key = request.POST['electronic_signature_key']
                archive = None
                if 'certificate' in request.FILES:
                    archive = request.FILES['certificate'].file
                elif instance.pk is not None and instance.electronic_signature:
                    archive = open(instance.electronic_signature.path, 'rb')
                if archive:
                    with archive as file:
                        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(file.read(), electronic_signature_key.encode())
                        for s in certificate.subject:
                            data[s.oid._name] = s.value
                        public_key = certificate.public_key().public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode('utf-8')
                        data['public_key'] = public_key
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Configuración de la Compañia'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        context['field_groups'] = build_field_groups(context['form'], COMPANY_FIELD_GROUPS)
        return context
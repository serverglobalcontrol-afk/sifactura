import json

from django.http import HttpResponse
from django.views.generic import UpdateView

from config import settings
from core.security.mixins import GroupPermissionMixin
from core.tenant.forms import CompanyForm, Company

EDITABLE_FIELDS = [
    'image', 'email_host', 'email_port', 'email_host_user', 'email_host_password',
    'backup_schedule_enabled', 'backup_schedule_frequency', 'backup_schedule_weekday', 'backup_schedule_time',
]

FIELD_GROUPS = [
    ('fas fa-clock', 'Respaldo automático', [
        'backup_schedule_enabled', 'backup_schedule_frequency', 'backup_schedule_weekday', 'backup_schedule_time',
    ]),
    ('fas fa-building', 'Datos generales', [
        'ruc', 'business_name', 'tradename', 'mobile', 'phone', 'email', 'website', 'description',
    ]),
    ('fas fa-file-invoice', 'Datos para el SRI', [
        'main_address', 'establishment_address', 'establishment_code', 'issuing_point_code', 'special_taxpayer',
        'obligated_accounting', 'environment_type', 'emission_type', 'retention_agent', 'regimen_rimpe',
        'iva', 'vat_percentage',
    ]),
    ('fas fa-file-signature', 'Logo y firma electrónica', [
        'image', 'electronic_signature', 'electronic_signature_key',
    ]),
    ('fas fa-envelope', 'Configuración de correo', [
        'email_host', 'email_port', 'email_host_user', 'email_host_password',
    ]),
    ('fas fa-toolbox', 'Plan y datos del sistema', [
        'schema_name', 'plan', 'plan_start_date', 'plan_end_date', 'representative_name', 'representative_position',
    ]),
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
        form = context['form']
        context['field_groups'] = [
            (icon, label, [form[name] for name in names if name in form.fields])
            for icon, label, names in FIELD_GROUPS
        ]
        return context
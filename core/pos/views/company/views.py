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
        return context
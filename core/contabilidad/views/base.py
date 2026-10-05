import json

from django.http import HttpResponse
from django.views.generic import CreateView, DeleteView, TemplateView, UpdateView

from core.contabilidad.mixins import AccountingEnabledMixin
from core.security.mixins import GroupPermissionMixin


def json_response(data):
    return HttpResponse(json.dumps(data), content_type='application/json')


class BaseListView(AccountingEnabledMixin, GroupPermissionMixin, TemplateView):
    """Listado con DataTables: el GET entrega la página y el POST
    action=search devuelve las filas como JSON (patrón de todo el sistema)."""
    model = None
    title = ''
    create_url = None

    def get_queryset(self):
        return self.model.objects.all()

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'search':
                data = [i.toJSON() for i in self.get_queryset()]
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.title
        context['create_url'] = self.create_url
        return context


class BaseCreateView(AccountingEnabledMixin, GroupPermissionMixin, CreateView):
    template_name = 'contabilidad/form.html'
    title = ''
    success_url = None

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'add':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['list_url'] = self.success_url
        context['title'] = self.title
        context['action'] = 'add'
        return context


class BaseUpdateView(AccountingEnabledMixin, GroupPermissionMixin, UpdateView):
    template_name = 'contabilidad/form.html'
    title = ''
    success_url = None

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST['action'] == 'edit':
                data = self.get_form().save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['list_url'] = self.success_url
        context['title'] = self.title
        context['action'] = 'edit'
        return context


class BaseDeleteView(AccountingEnabledMixin, GroupPermissionMixin, DeleteView):
    template_name = 'delete.html'
    success_url = None

    def check_deletable(self, obj):
        """Lanza ValueError con un mensaje legible si no se puede borrar."""

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            obj = self.get_object()
            self.check_deletable(obj)
            obj.delete()
        except Exception as e:
            from django.db.models import ProtectedError
            if isinstance(e, ProtectedError):
                data['error'] = 'No se puede eliminar: ya tiene movimientos o está en uso.'
            else:
                data['error'] = str(e)
        return json_response(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context

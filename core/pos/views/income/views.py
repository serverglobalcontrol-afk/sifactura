import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, FormView

from core.pos.forms import IncomeForm, Income
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class IncomeListView(GroupPermissionMixin, FormView):
    template_name = 'income/list.html'
    form_class = ReportForm
    permission_required = 'view_income'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = Income.objects.filter()
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Ingresos'
        context['create_url'] = reverse_lazy('income_create')
        return context


class IncomeCreateView(GroupPermissionMixin, CreateView):
    model = Income
    template_name = 'income/create.html'
    form_class = IncomeForm
    success_url = reverse_lazy('income_list')
    permission_required = 'add_income'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                form = self.get_form()
                # is_valid() hay que llamarlo ANTES de fijar created_by: la
                # primera vez que corre reconstruye self.instance completo
                # desde cleaned_data (sin created_by, porque no viene en el
                # POST), pisando cualquier valor que se le haya puesto antes.
                # Llamadas posteriores a is_valid()/form.save() ya no vuelven
                # a ejecutar esa reconstrucción -Django cachea el resultado-,
                # así que fijarlo aquí sí se conserva hasta guardar.
                if form.is_valid():
                    form.instance.created_by = request.user
                data = form.save()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Ingreso'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class IncomeUpdateView(GroupPermissionMixin, UpdateView):
    model = Income
    template_name = 'income/create.html'
    form_class = IncomeForm
    success_url = reverse_lazy('income_list')
    permission_required = 'change_income'

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
        context['title'] = 'Edición de un Ingreso'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class IncomeDeleteView(GroupPermissionMixin, DeleteView):
    model = Income
    template_name = 'delete.html'
    success_url = reverse_lazy('income_list')
    permission_required = 'delete_income'

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

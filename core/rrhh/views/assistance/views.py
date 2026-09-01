import json
from datetime import datetime
from io import BytesIO

import xlsxwriter
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import FormView, CreateView, TemplateView

from core.rrhh.forms import AssistanceForm, Assistance, Employee, AssistanceDetail
from core.security.mixins import GroupPermissionMixin


class AssistanceListView(GroupPermissionMixin, FormView):
    form_class = AssistanceForm
    template_name = 'assistance/admin/list.html'
    permission_required = 'view_assistance'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = AssistanceDetail.objects.all()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(assistance__date_joined__range=[start_date, end_date])
                for i in queryset.order_by('assistance__date_joined'):
                    data.append(i.toJSON())
            elif action == 'export_assistences_excel':
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = AssistanceDetail.objects.all()
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(assistance__date_joined__range=[start_date, end_date])
                headers = {
                    'Fecha de asistencia': 35,
                    'Empleado': 35,
                    'Número de documento': 35,
                    'Cargo': 35,
                    'Area': 35,
                    'Observación': 55,
                    'Asistencia': 35,
                }
                output = BytesIO()
                workbook = xlsxwriter.Workbook(output)
                worksheet = workbook.add_worksheet('asistencias')
                cell_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1})
                row_format = workbook.add_format({'align': 'center', 'border': 1})
                index = 0
                for name, width in headers.items():
                    worksheet.set_column(first_col=0, last_col=index, width=width)
                    worksheet.write(0, index, name, cell_format)
                    index += 1
                row = 1
                for i in queryset.order_by('assistance__date_joined'):
                    worksheet.write(row, 0, i.assistance.date_joined_format(), row_format)
                    worksheet.write(row, 1, i.employee.user.names, row_format)
                    worksheet.write(row, 2, i.employee.dni, row_format)
                    worksheet.write(row, 3, i.employee.position.name, row_format)
                    worksheet.write(row, 4, i.employee.area.name, row_format)
                    worksheet.write(row, 5, i.description, row_format)
                    worksheet.write(row, 6, 'Si' if i.state else 'No', row_format)
                    row += 1
                workbook.close()
                output.seek(0)
                response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                response['Content-Disposition'] = f"attachment; filename='ASISTENCIAS_{datetime.now().date().strftime('%d_%m_%Y')}.xlsx'"
                return response
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Asistencias'
        context['create_url'] = reverse_lazy('assistance_create')
        return context


class AssistanceCreateView(GroupPermissionMixin, CreateView):
    model = Assistance
    template_name = 'assistance/admin/create.html'
    form_class = AssistanceForm
    success_url = reverse_lazy('assistance_list')
    permission_required = 'add_assistance'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                with transaction.atomic():
                    date_joined = datetime.strptime(request.POST['date_joined'], '%Y-%m-%d')
                    assistance = Assistance()
                    assistance.date_joined = date_joined
                    assistance.year = date_joined.year
                    assistance.month = date_joined.month
                    assistance.day = date_joined.day
                    assistance.save()
                    for i in json.loads(request.POST['assistances']):
                        detail = AssistanceDetail()
                        detail.assistance_id = assistance.id
                        detail.employee_id = int(i['id'])
                        detail.description = i['description']
                        detail.state = i['state']
                        detail.save()
            elif action == 'generate_assistance':
                data = []
                for i in Employee.objects.filter(user__is_active=True):
                    item = i.toJSON()
                    item['state'] = 0
                    item['description'] = ''
                    data.append(item)
            elif action == 'validate_data':
                data = {'valid': not Assistance.objects.filter(date_joined=request.POST['date_joined'].strip()).exists()}
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de una Asistencia'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class AssistanceUpdateView(GroupPermissionMixin, FormView):
    template_name = 'assistance/admin/create.html'
    form_class = AssistanceForm
    success_url = reverse_lazy('assistance_list')
    permission_required = 'change_assistance'

    def get_form(self, form_class=None):
        form = AssistanceForm(initial={'date_joined': self.kwargs['date_joined']})
        form.fields['date_joined'].widget.attrs.update({'disabled': True})
        return form

    def get_object(self):
        return Assistance.objects.filter(date_joined=self.kwargs['date_joined']).first()

    def get(self, request, *args, **kwargs):
        if self.get_object() is not None:
            return super(AssistanceUpdateView, self).get(request, *args, **kwargs)
        messages.error(request, f"No se puede editar las asistencia del dia {self.kwargs['date_joined']} porque no existen")
        return HttpResponseRedirect(self.success_url)

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                with transaction.atomic():
                    for i in json.loads(request.POST['assistances']):
                        if 'pk' in i:
                            detail = AssistanceDetail.objects.get(pk=i['pk'])
                        else:
                            date_joined = datetime.strptime(self.kwargs['date_joined'], '%Y-%m-%d')
                            assistance = Assistance.objects.get_or_create(date_joined=date_joined, year=date_joined.year, month=date_joined.month, day=date_joined.day)[0]
                            detail = AssistanceDetail()
                            detail.assistance_id = assistance.id
                        detail.employee_id = i['id']
                        detail.description = i['description']
                        detail.state = i['state']
                        detail.save()
            elif action == 'generate_assistance':
                data = []
                date_joined = self.kwargs['date_joined']
                for i in Employee.objects.filter(user__is_active=True):
                    item = i.toJSON()
                    item['state'] = 0
                    item['description'] = ''
                    assistance_detail = AssistanceDetail.objects.filter(assistance__date_joined=date_joined, employee_id=i.id).first()
                    if assistance_detail:
                        item['pk'] = assistance_detail.id
                        item['state'] = 1 if assistance_detail.state else 0
                        item['description'] = assistance_detail.description
                    data.append(item)
            elif action == 'validate_data':
                data = {'valid': not Assistance.objects.filter(date_joined=request.POST['date_joined']).exclude(date_joined=self.kwargs['date_joined']).exists()}
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de una Asistencia'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        return context


class AssistanceDeleteView(GroupPermissionMixin, TemplateView):
    template_name = 'delete.html'
    success_url = reverse_lazy('assistance_list')
    permission_required = 'delete_assistance'

    def get(self, request, *args, **kwargs):
        if self.get_object() is not None:
            return super(AssistanceDeleteView, self).get(request, *args, **kwargs)
        messages.error(request, 'No existen asistencias en el rango de fechas ingresadas')
        return HttpResponseRedirect(self.success_url)

    def get_object(self, queryset=None):
        start_date = self.kwargs['start_date']
        end_date = self.kwargs['end_date']
        return Assistance.objects.filter(date_joined__range=[start_date, end_date]).first()

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
        context['start_date'] = self.kwargs['start_date']
        context['end_date'] = self.kwargs['end_date']
        return context


class AssistanceEmployeeListView(GroupPermissionMixin, FormView):
    form_class = AssistanceForm
    template_name = 'assistance/employee/list.html'
    permission_required = 'view_employee_assistance'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search':
                data = []
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                queryset = AssistanceDetail.objects.filter(employee__user=request.user)
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(assistance__date_joined__range=[start_date, end_date])
                for i in queryset.order_by('assistance__date_joined'):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Asistencias'
        return context

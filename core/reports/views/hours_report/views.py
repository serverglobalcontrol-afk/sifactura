import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import FormView, View

from core.pos.utilities import printer
from core.reports.forms import HoursReportForm, HoursDetailReportForm
from core.rrhh.models import AssistanceDetail, Employee, MONTHLY_WORK_HOURS
from core.security.mixins import GroupModuleMixin
from core.tenant.models import Company


def build_hours_summary(start_date, end_date, employee_id=None):
    queryset = AssistanceDetail.objects.filter(state=True).select_related('employee__user', 'assistance')
    if start_date and end_date:
        queryset = queryset.filter(assistance__date_joined__range=[start_date, end_date])
    if employee_id:
        queryset = queryset.filter(employee_id__in=employee_id)
    summary = {}
    for detail in queryset.order_by('assistance__date_joined'):
        employee = detail.employee
        if employee.id not in summary:
            summary[employee.id] = {
                'employee': employee.toJSON(),
                'days_worked': 0,
                'regular_hours': 0.0,
                'overtime_hours': 0.0,
            }
        item = summary[employee.id]
        item['days_worked'] += 1
        item['regular_hours'] += detail.get_regular_hours()
        item['overtime_hours'] += detail.get_overtime_hours()
    data = list(summary.values())
    for item in data:
        hourly_rate = item['employee']['remuneration'] and (item['employee']['remuneration'] / MONTHLY_WORK_HOURS) or 0
        item['regular_hours'] = round(item['regular_hours'], 2)
        item['overtime_hours'] = round(item['overtime_hours'], 2)
        item['hourly_rate'] = round(hourly_rate, 4)
        item['overtime_value'] = round(item['overtime_hours'] * hourly_rate * 1.5, 2)
        item['total_hours'] = round(item['regular_hours'] + item['overtime_hours'], 2)
        item['total_value'] = round((item['regular_hours'] * hourly_rate) + item['overtime_value'], 2)
    return data


def build_hours_detail(employee, start_date, end_date):
    queryset = AssistanceDetail.objects.filter(employee=employee).select_related('assistance', 'employee')
    if start_date and end_date:
        queryset = queryset.filter(assistance__date_joined__range=[start_date, end_date])
    data = []
    for detail in queryset.order_by('assistance__date_joined'):
        data.append({
            'date_joined': detail.assistance.date_joined_format(),
            'state': detail.state,
            'description': detail.description,
            'scheduled_check_in': employee.scheduled_check_in_format(),
            'check_in': detail.check_in_format(),
            'late_minutes': detail.get_late_minutes(),
            'scheduled_check_out': employee.scheduled_check_out_format(),
            'check_out': detail.check_out_format(),
            'early_departure_minutes': detail.get_early_departure_minutes(),
            'hours_worked': detail.get_hours_worked(),
            'overtime_hours': detail.get_overtime_hours(),
        })
    return data


class HoursReportView(GroupModuleMixin, FormView):
    template_name = 'hours_report/report.html'
    form_class = HoursReportForm

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                start_date = request.POST.get('start_date')
                end_date = request.POST.get('end_date')
                employee_id = json.loads(request.POST.get('employee_id', '[]'))
                data = build_hours_summary(start_date, end_date, employee_id)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Horas Trabajadas'
        return context


class HoursReportPrintView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        employee_id = [i for i in request.GET.get('employee_id', '').split(',') if i]
        data = build_hours_summary(start_date, end_date, employee_id)
        context = {
            'company': Company.objects.first(),
            'data': data,
            'start_date': start_date,
            'end_date': end_date,
            'printed_by': request.user.names,
            'printed_at': timezone.localtime().strftime('%Y-%m-%d %H:%M'),
            'totals': {
                'days_worked': sum(i['days_worked'] for i in data),
                'regular_hours': round(sum(i['regular_hours'] for i in data), 2),
                'overtime_hours': round(sum(i['overtime_hours'] for i in data), 2),
                'total_hours': round(sum(i['total_hours'] for i in data), 2),
                'overtime_value': round(sum(i['overtime_value'] for i in data), 2),
                'total_value': round(sum(i['total_value'] for i in data), 2),
            },
        }
        pdf_file = printer.create_pdf(context=context, template_name='hours_report/report_pdf.html')
        return HttpResponse(pdf_file, content_type='application/pdf')


class HoursDetailReportView(GroupModuleMixin, FormView):
    template_name = 'hours_report/detail_report.html'
    form_class = HoursDetailReportForm

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_report':
                start_date = request.POST.get('start_date')
                end_date = request.POST.get('end_date')
                employee = get_object_or_404(Employee, pk=request.POST['employee_id'])
                data = build_hours_detail(employee, start_date, end_date)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Reporte de Marcaciones por Empleado'
        return context


class HoursDetailReportPrintView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        employee = get_object_or_404(Employee, pk=request.GET.get('employee_id'))
        data = build_hours_detail(employee, start_date, end_date)
        totals = {
            'days_worked': sum(1 for i in data if i['state']),
            'late_days': sum(1 for i in data if i['late_minutes'] > 0),
            'early_departure_days': sum(1 for i in data if i['early_departure_minutes'] > 0),
            'hours_worked': round(sum(i['hours_worked'] for i in data), 2),
            'overtime_hours': round(sum(i['overtime_hours'] for i in data), 2),
        }
        context = {
            'company': Company.objects.first(),
            'employee': employee,
            'data': data,
            'start_date': start_date,
            'end_date': end_date,
            'printed_by': request.user.names,
            'printed_at': timezone.localtime().strftime('%Y-%m-%d %H:%M'),
            'totals': totals,
        }
        pdf_file = printer.create_pdf(context=context, template_name='hours_report/detail_report_pdf.html')
        return HttpResponse(pdf_file, content_type='application/pdf')

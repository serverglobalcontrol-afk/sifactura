import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DeleteView, CreateView, FormView

from core.pos.forms import PaymentsDebtsPayForm, DebtsPay, PaymentsDebtsPay
from core.pos.utilities.pdf_creator import PDFCreator
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin
from core.tenant.models import Company


class DebtsPayListView(GroupPermissionMixin, FormView):
    template_name = 'debts_pay/list.html'
    form_class = ReportForm
    permission_required = 'view_debts_pay'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = DebtsPay.objects.filter()
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_pays':
                data = []
                for count, i in enumerate(PaymentsDebtsPay.objects.filter(debts_pay_id=request.POST['id']).order_by('id')):
                    item = i.toJSON()
                    item['index'] = count + 1
                    data.append(item)
            elif action == 'delete_pay':
                id = request.POST['id']
                payment = PaymentsDebtsPay.objects.get(pk=id)
                debtspay = payment.debts_pay
                payment.delete()
                debtspay.validate_debt()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Cuentas por Pagar'
        context['create_url'] = reverse_lazy('debts_pay_create')
        return context


class DebtsPayCreateView(GroupPermissionMixin, CreateView):
    model = DebtsPay
    template_name = 'debts_pay/create.html'
    form_class = PaymentsDebtsPayForm
    success_url = reverse_lazy('debts_pay_list')
    permission_required = 'add_debts_pay'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_debts_pay':
                data = []
                term = request.POST['term']
                for i in DebtsPay.objects.filter(Q(purchase__provider__name__icontains=term) | Q(purchase__number__icontains=term)).exclude(state=False)[0:10]:
                    item = i.toJSON()
                    item['text'] = i.get_full_name()
                    data.append(item)
            elif action == 'add':
                with transaction.atomic():
                    payment = PaymentsDebtsPay()
                    payment.created_by_id = request.user.id
                    payment.debts_pay_id = int(request.POST['debts_pay'])
                    payment.date_joined = request.POST['date_joined']
                    payment.payment_type = request.POST['payment_type']
                    payment.bank_entity = request.POST.get('bank_entity')
                    payment.reference_number = request.POST.get('reference_number')
                    payment.valor = float(request.POST['valor'])
                    payment.description = request.POST['description']
                    payment.save()
                    payment.debts_pay.validate_debt()
                    data['print_url'] = str(reverse_lazy('debts_pay_print', kwargs={'pk': payment.id}))
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Pago'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        return context


class DebtsPayDeleteView(GroupPermissionMixin, DeleteView):
    model = DebtsPay
    template_name = 'delete.html'
    success_url = reverse_lazy('debts_pay_list')
    permission_required = 'delete_debts_pay'

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


class DebtsPayPrintView(LoginRequiredMixin, View):
    success_url = reverse_lazy('debts_pay_list')

    def get(self, request, *args, **kwargs):
        try:
            payment = PaymentsDebtsPay.objects.get(id=self.kwargs['pk'])
            # Alto dinámico (igual que el ticket de venta): la hoja se ajusta al
            # contenido en vez de tener una altura fija que corta a una segunda
            # página en blanco cuando aparecen las líneas de banco/referencia.
            height = 480
            if payment.payment_type in ('transfer', 'deposit', 'check'):
                height += 45
            pdf = PDFCreator(template_name='debts_pay/ticket.html')
            pdf_file = pdf.create(context={'doc': payment, 'obj': payment, 'company': Company.objects.first(), 'height': height})
            return HttpResponse(pdf_file, content_type='application/pdf')
        except Exception as e:
            messages.error(request, str(e))

        return HttpResponseRedirect(self.success_url)

import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import DeleteView, CreateView, FormView

from core.pos.forms import PaymentsCtaCollectForm, CtasCollect, PaymentsCtaCollect
from core.pos.utilities import printer
from core.pos.utilities.pdf_creator import PDFCreator
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin


class CtasCollectListView(GroupPermissionMixin, FormView):
    template_name = 'ctas_collect/list.html'
    form_class = ReportForm
    permission_required = 'view_ctas_collect'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = CtasCollect.objects.filter()
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            elif action == 'search_pays':
                data = []
                for count, i in enumerate(PaymentsCtaCollect.objects.filter(ctas_collect_id=request.POST['id']).order_by('id')):
                    item = i.toJSON()
                    item['index'] = count + 1
                    data.append(item)
            elif action == 'delete_pay':
                id = request.POST['id']
                payment = PaymentsCtaCollect.objects.get(pk=id)
                ctascollect = payment.ctas_collect
                payment.delete()
                ctascollect.recalculate_details()
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Cuentas por Cobrar'
        context['create_url'] = reverse_lazy('ctas_collect_create')
        return context


class CtasCollectCreateView(GroupPermissionMixin, CreateView):
    model = CtasCollect
    template_name = 'ctas_collect/create.html'
    form_class = PaymentsCtaCollectForm
    success_url = reverse_lazy('ctas_collect_list')
    permission_required = 'add_ctas_collect'

    def post(self, request, *args, **kwargs):
        action = request.POST['action']
        data = {}
        try:
            if action == 'search_ctas_collect':
                data = []
                term = request.POST['term']
                filters = Q(
                    Q(sale__voucher_number__icontains=term) |
                    Q(sale__voucher_number_full__icontains=term) |
                    Q(sale__client__user__names__icontains=term) |
                    Q(sale__client__dni__icontains=term)
                )
                for i in CtasCollect.objects.filter(filters).exclude(state=False)[0:10]:
                    item = i.toJSON()
                    item['text'] = i.get_full_name()
                    data.append(item)
            elif action == 'add':
                with transaction.atomic():
                    payment = PaymentsCtaCollect()
                    payment.created_by_id = request.user.id
                    payment.ctas_collect_id = int(request.POST['ctas_collect'])
                    payment.date_joined = request.POST['date_joined']
                    payment.payment_type = request.POST['payment_type']
                    payment.bank_entity = request.POST.get('bank_entity')
                    payment.reference_number = request.POST.get('reference_number')
                    payment.valor = float(request.POST['valor'])
                    payment.description = request.POST['description']
                    payment.save()
                    payment.ctas_collect.recalculate_details()
                    data['print_url'] = str(reverse_lazy('ctas_collect_print', kwargs={'pk': payment.id}))
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


class CtasCollectDeleteView(GroupPermissionMixin, DeleteView):
    model = CtasCollect
    template_name = 'delete.html'
    success_url = reverse_lazy('ctas_collect_list')
    permission_required = 'delete_ctas_collect'

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


class CtasCollectPrintView(LoginRequiredMixin, View):
    success_url = reverse_lazy('ctas_collect_list')

    def get(self, request, *args, **kwargs):
        try:
            payment = PaymentsCtaCollect.objects.get(id=self.kwargs['pk'])
            # Alto dinámico (igual que el ticket de venta): la hoja se ajusta al
            # contenido en vez de tener una altura fija que corta a una segunda
            # página en blanco cuando aparecen las líneas de banco/referencia.
            height = 520
            if payment.payment_type in ('transfer', 'deposit', 'check'):
                height += 45
            pdf = PDFCreator(template_name='ctas_collect/ticket.html')
            pdf_file = pdf.create(context={'doc': payment, 'obj': payment, 'height': height})
            return HttpResponse(pdf_file, content_type='application/pdf')
        except Exception as e:
            messages.error(request, str(e))

        return HttpResponseRedirect(self.success_url)

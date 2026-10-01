import json
from datetime import date, datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import FormView

from config import settings
from core.pos.models import CashRegister
from core.pos.utilities import printer
from core.reports.forms import ReportForm
from core.security.mixins import GroupModuleMixin


class CashRegisterOpeningView(LoginRequiredMixin, View):
    template_name = 'cash_register/opening.html'

    def get(self, request, *args, **kwargs):
        if CashRegister.objects.filter(user=request.user, date_joined=date.today(), status='open').exists():
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        # Si en el último cierre el cajero dejó designado un valor para hoy,
        # se sugiere como apertura (pero se puede ajustar si el conteo real
        # no coincide).
        last_register = CashRegister.objects.filter(user=request.user, status='closed', next_opening_amount__isnull=False).order_by('-date_joined', '-closing_datetime').first()
        return render(request, self.template_name, {
            'title': 'Apertura de Caja',
            'list_url': settings.LOGIN_REDIRECT_URL,
            'last_register': last_register,
        })

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if CashRegister.objects.filter(user=request.user, date_joined=date.today(), status='open').exists():
                data['error'] = 'Ya tienes una caja abierta hoy'
            else:
                CashRegister.objects.create(
                    user=request.user,
                    date_joined=date.today(),
                    opening_amount=float(request.POST['opening_amount']),
                    opening_notes=request.POST.get('opening_notes'),
                )
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')


class CashRegisterClosingView(LoginRequiredMixin, View):
    template_name = 'cash_register/closing.html'

    def get_open_register(self, request):
        return CashRegister.objects.filter(user=request.user, date_joined=date.today(), status='open').first()

    def get(self, request, *args, **kwargs):
        register = self.get_open_register(request)
        if not register:
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        return render(request, self.template_name, {
            'title': 'Cierre de Caja',
            'list_url': settings.LOGIN_REDIRECT_URL,
            'register': register,
            'breakdown': register.calculate_breakdown(),
        })

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            register = self.get_open_register(request)
            if not register:
                data['error'] = 'No tienes ninguna caja abierta'
            else:
                counted_amount = float(request.POST['counted_amount'])
                next_opening_amount_raw = (request.POST.get('next_opening_amount') or '').strip()
                next_opening_amount = float(next_opening_amount_raw) if next_opening_amount_raw else None
                if next_opening_amount is not None:
                    # El valor que se deja para la próxima apertura tiene que
                    # salir del efectivo que de verdad se contó hoy: no puede
                    # ser negativo ni mayor a lo que hay en caja.
                    if next_opening_amount < 0:
                        raise ValueError('El valor para la próxima apertura no puede ser negativo')
                    if next_opening_amount > counted_amount:
                        raise ValueError('El valor para la próxima apertura no puede ser mayor al efectivo contado')
                register.close(
                    counted_amount=counted_amount,
                    closing_notes=request.POST.get('closing_notes'),
                    next_opening_amount=next_opening_amount,
                )
                # Antes se cerraba sesión en este mismo paso. Ahora se deja la
                # sesión viva y se manda a una pantalla de confirmación con la
                # opción de imprimir el cierre -el cajero decide si imprime o
                # no antes de salir-; el logout real queda a cargo del botón
                # "Cerrar sesión" de esa pantalla (LoginLogoutRedirectView, que
                # ya no encuentra ninguna caja abierta y deja salir normal).
                data['redirect_url'] = str(reverse_lazy('cash_register_closed', kwargs={'pk': register.id}))
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')


class CashRegisterClosedView(LoginRequiredMixin, View):
    template_name = 'cash_register/closed.html'

    def get(self, request, *args, **kwargs):
        register = CashRegister.objects.filter(pk=kwargs['pk'], user=request.user, status='closed').first()
        if not register:
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        return render(request, self.template_name, {
            'title': 'Cierre de Caja Completado',
            'register': register,
            'breakdown': register.breakdown,
        })


class CashRegisterPrintView(LoginRequiredMixin, View):
    # Reimprimir un cierre -tanto justo después de cerrarlo como desde el
    # historial, días después-. Siempre se genera al vuelo desde el
    # breakdown que quedó guardado en el cierre, nunca se recalcula ni se
    # guarda en storage -no hace falta: es barato de regenerar y así un
    # cierre viejo nunca cambia aunque se vuelva a imprimir.
    def get(self, request, *args, **kwargs):
        register = CashRegister.objects.filter(pk=kwargs['pk'], status='closed').select_related('user').first()
        if not register:
            raise Http404
        is_owner = register.user_id == request.user.id
        if not is_owner and not request.user.has_perm('pos.view_cashregister'):
            raise Http404
        context = {
            'company': request.tenant.company,
            'register': register,
            'breakdown': register.breakdown,
            'printed_by': request.user.names,
            'printed_at': timezone.localtime().strftime('%Y-%m-%d %H:%M'),
        }
        pdf_file = printer.create_pdf(context=context, template_name='cash_register/format/closing.html')
        return HttpResponse(pdf_file, content_type='application/pdf')


class CashRegisterListView(GroupModuleMixin, FormView):
    # "Mis Cierres de Caja": cada usuario ve solo su propio historial, el
    # mismo criterio de "cada caja cuadra independiente" ya usado en todo el
    # cuadre de caja.
    template_name = 'cash_register/list.html'
    form_class = ReportForm

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = CashRegister.objects.filter(user=request.user, status='closed')
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset.order_by('-date_joined', '-id'):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Mis Cierres de Caja'
        return context


class CashRegisterGeneralListView(GroupModuleMixin, FormView):
    # Mismo módulo/alcance que el Consolidado del Dashboard: no está en
    # POINT_OF_SALE_URLS, así que solo Administrador llega hasta acá -Punto
    # de Venta ni siquiera lo ve en el menú.
    template_name = 'cash_register/general_list.html'
    form_class = ReportForm

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = CashRegister.objects.filter(status='closed').select_related('user')
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset.order_by('-date_joined', 'user__username'):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Cierres de Caja (General)'
        return context


class CashRegisterConsolidatedPrintView(LoginRequiredMixin, View):
    # Cierre consolidado de un día: suma todas las cajas CERRADAS de ese día
    # (no recalcula movimientos sueltos de cajas que sigan abiertas), con el
    # mismo desglose por usuario que ya usa "Cajas del día de hoy" en el
    # Dashboard.
    def get(self, request, *args, **kwargs):
        if not request.user.has_perm('pos.view_cashregister'):
            raise Http404
        selected_date = datetime.strptime(kwargs['date'], '%Y-%m-%d').date()
        registers = CashRegister.objects.filter(date_joined=selected_date, status='closed').select_related('user').order_by('user__username')
        if not registers.exists():
            raise Http404
        opening_amount_total = registers.aggregate(r=Coalesce(Sum('opening_amount'), 0.00, output_field=FloatField()))['r']
        consolidated_breakdown = CashRegister.compute_breakdown(selected_date, opening_amount=opening_amount_total)
        context = {
            'company': request.tenant.company,
            'date_joined': selected_date,
            'registers': registers,
            'breakdown': consolidated_breakdown,
            'printed_by': request.user.names,
            'printed_at': timezone.localtime().strftime('%Y-%m-%d %H:%M'),
        }
        pdf_file = printer.create_pdf(context=context, template_name='cash_register/format/consolidated.html')
        return HttpResponse(pdf_file, content_type='application/pdf')

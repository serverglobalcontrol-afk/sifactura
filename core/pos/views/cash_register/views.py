import json
from datetime import date

from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View

from config import settings
from core.pos.models import CashRegister


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
                logout(request)
                data['redirect_url'] = str(reverse_lazy('login'))
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

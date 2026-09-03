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
        return render(request, self.template_name, {'title': 'Apertura de Caja', 'list_url': settings.LOGIN_REDIRECT_URL})

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
                register.close(
                    counted_amount=float(request.POST['counted_amount']),
                    closing_notes=request.POST.get('closing_notes'),
                )
                logout(request)
                data['redirect_url'] = str(reverse_lazy('login'))
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

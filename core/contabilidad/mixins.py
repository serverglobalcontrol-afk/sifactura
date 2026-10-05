from django.contrib import messages
from django.http import HttpResponseRedirect

from config import settings
from core.contabilidad.services.gate import is_enabled


class AccountingEnabledMixin:
    """Defensa en profundidad: aunque el menú ya no muestre el módulo, una
    URL escrita a mano no debe funcionar en una empresa que no lleva
    contabilidad. Va ANTES de GroupPermissionMixin/GroupModuleMixin en la
    herencia."""

    def dispatch(self, request, *args, **kwargs):
        if not is_enabled():
            messages.error(request, 'La contabilidad no está habilitada para esta empresa.')
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)

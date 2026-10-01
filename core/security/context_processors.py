from datetime import date, datetime

from django_tenants.utils import schema_context

from core.pos.models import CashRegister
from core.security.models import Dashboard
from core.tenant.models import ElectronicInvoicingProvider


def site_settings(request):
    dashboard = Dashboard.objects.first()
    # Aunque cada schema (empresa) tiene su propia copia física de esta
    # tabla, el dato real solo se administra desde admin.localhost (schema
    # public). Se lee siempre de ahí para que todas las compañías hereden el
    # mismo nombre y logo del sistema, sin tener que repetirlo por empresa.
    with schema_context('public'):
        electronic_invoicing_provider = ElectronicInvoicingProvider.objects.first()
    parameters = {
        'dashboard': dashboard,
        'date_joined': datetime.now(),
        'menu': 'hzt_body.html' if dashboard is None else dashboard.get_template_from_layout(),
        'electronic_invoicing_provider': electronic_invoicing_provider,
    }
    if hasattr(request.tenant, 'company'):
        parameters['company'] = request.tenant.company
    # Disponible en CUALQUIER página (no solo el Dashboard) para poder
    # mostrar el botón "Cerrar Caja" en el navbar: el cierre definitivo ya
    # no depende de cerrar sesión (ver LoginLogoutRedirectView), así que
    # necesita un acceso directo visible en todo momento mientras la caja
    # del día siga abierta.
    if request.user.is_authenticated and not request.tenant.is_public():
        parameters['open_cash_register'] = CashRegister.objects.filter(
            user=request.user, date_joined=date.today(), status='open'
        ).first()
    return parameters

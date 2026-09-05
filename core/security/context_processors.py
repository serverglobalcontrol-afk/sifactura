from datetime import datetime

from core.security.models import Dashboard
from core.tenant.models import ElectronicInvoicingProvider


def site_settings(request):
    dashboard = Dashboard.objects.first()
    parameters = {
        'dashboard': dashboard,
        'date_joined': datetime.now(),
        'menu': 'hzt_body.html' if dashboard is None else dashboard.get_template_from_layout(),
        # Nombre del sistema (marca del software, no de la compañía del
        # tenant): se muestra en la parte superior del menú en todas las
        # vistas, tomado de la página Proveedor de Facturación Electrónica.
        'electronic_invoicing_provider': ElectronicInvoicingProvider.objects.first(),
    }
    if hasattr(request.tenant, 'company'):
        parameters['company'] = request.tenant.company
    return parameters

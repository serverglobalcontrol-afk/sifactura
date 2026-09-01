from datetime import datetime

from core.security.models import Dashboard


def site_settings(request):
    dashboard = Dashboard.objects.first()
    parameters = {
        'dashboard': dashboard,
        'date_joined': datetime.now(),
        'menu': 'hzt_body.html' if dashboard is None else dashboard.get_template_from_layout()
    }
    if hasattr(request.tenant, 'company'):
        parameters['company'] = request.tenant.company
    return parameters

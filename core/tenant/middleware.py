from django.http import HttpResponseForbidden
from django_tenants.middleware import TenantMiddleware


class CustomTenantMiddleware(TenantMiddleware):
    def process_request(self, request):
        super().process_request(request)
        if hasattr(request, 'tenant') and hasattr(request.tenant, 'company'):
            company = request.tenant.company
            if not company.active:
                return HttpResponseForbidden('Esta compañía está inactiva y no puede acceder al sistema')

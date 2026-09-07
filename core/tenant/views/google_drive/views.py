import json

from django.contrib import messages
from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect
from django.views import View
from django_tenants.utils import schema_context

from core.security.mixins import GroupPermissionMixin
from core.tenant import google_drive
from core.tenant.models import Company, ElectronicInvoicingProvider

STATE_SALT = 'google-drive-oauth'
STATE_MAX_AGE = 600  # 10 minutos: tiempo máximo para completar el consentimiento en Google


def _resolve_target(scope, request):
    if scope == 'system':
        return ElectronicInvoicingProvider.objects.first()
    return getattr(request.tenant, 'company', None)


class GoogleDriveConnectView(GroupPermissionMixin, View):
    def get_permissions(self):
        return ['change_electronicinvoicingprovider'] if self.kwargs.get('scope') == 'system' else ['change_company']

    def get(self, request, *args, **kwargs):
        scope = kwargs.get('scope')
        return_url = request.META.get('HTTP_REFERER') or '/'
        if not google_drive.is_configured():
            messages.error(request, 'La integración con Google Drive no está configurada en el servidor.')
            return HttpResponseRedirect(return_url)
        target = _resolve_target(scope, request)
        if not target or not target.pk:
            messages.error(request, 'Primero debes guardar los datos antes de conectar Google Drive.')
            return HttpResponseRedirect(return_url)
        state = signing.dumps({
            'scope': scope,
            'object_id': target.pk,
            'return_url': return_url,
        }, salt=STATE_SALT)
        return HttpResponseRedirect(google_drive.build_authorization_url(state))


class GoogleDriveCallbackView(View):
    """Recibe el redireccionamiento de Google. Se accede siempre desde una
    única URL fija (no desde el subdominio de cada compañía), por lo que no
    depende de la sesión: la autorización viaja firmada dentro de 'state'."""

    def get(self, request, *args, **kwargs):
        state_raw = request.GET.get('state', '')
        try:
            state = signing.loads(state_raw, salt=STATE_SALT, max_age=STATE_MAX_AGE)
        except signing.BadSignature:
            return HttpResponse('Solicitud inválida o expirada.', status=400)

        return_url = state.get('return_url') or '/'
        error = request.GET.get('error')
        if error:
            return HttpResponseRedirect(f'{return_url}?google_drive_error={error}')

        code = request.GET.get('code')
        with schema_context('public'):
            try:
                if state['scope'] == 'system':
                    target = ElectronicInvoicingProvider.objects.get(pk=state['object_id'])
                else:
                    target = Company.objects.get(pk=state['object_id'])
                tokens = google_drive.exchange_code_for_tokens(code)
                refresh_token = tokens.get('refresh_token')
                if not refresh_token:
                    raise Exception(
                        'Google no devolvió un token de actualización. '
                        'Revoca el acceso de la app en https://myaccount.google.com/permissions e inténtalo de nuevo.'
                    )
                access_token = tokens['access_token']
                folder_id = google_drive.get_or_create_folder(access_token, f'Respaldos Si-Factura - {target}')
                target.set_google_drive_refresh_token(refresh_token)
                target.google_drive_account_email = google_drive.get_account_email(access_token)
                target.google_drive_folder_id = folder_id
                target.save()
            except Exception as e:
                return HttpResponseRedirect(f'{return_url}?google_drive_error={e}')
        return HttpResponseRedirect(f'{return_url}?google_drive_connected=1')


class GoogleDriveDisconnectView(GroupPermissionMixin, View):
    def get_permissions(self):
        return ['change_electronicinvoicingprovider'] if self.kwargs.get('scope') == 'system' else ['change_company']

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            target = _resolve_target(kwargs.get('scope'), request)
            target.disconnect_google_drive()
            target.save()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

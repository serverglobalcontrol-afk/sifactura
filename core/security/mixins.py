from crum import get_current_request
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect

from config import settings


class GroupPermissionMixin(LoginRequiredMixin, object):
    redirect_field_name = settings.LOGIN_REDIRECT_URL
    permission_required = None

    def get_permissions(self):
        permissions = []
        if isinstance(self.permission_required, str):
            permissions.append(self.permission_required)
        else:
            permissions = list(self.permission_required)
        return permissions

    def get_last_url(self):
        request = get_current_request()
        if 'url_last' in request.session:
            if request.session['url_last'] != request.path:
                return request.session['url_last']
        return settings.LOGIN_REDIRECT_URL

    def dispatch(self, request, *args, **kwargs):
        # Se revisa en dispatch() (no en get()) para que la verificación de
        # permisos cubra TODAS las peticiones de esta vista -incluyendo
        # post()-, no solo la carga inicial de la página. Antes, una vista
        # con su propio post() (el caso de casi todas) se saltaba por
        # completo esta revisión.
        if 'group' not in request.session:
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        request.session['module'] = None
        group = request.session['group']
        permission_list = self.get_permissions()
        queryset = group.permissions.filter(codename__in=permission_list)
        if queryset.count() == len(permission_list):
            group_module = group.groupmodule_set.filter(module__permissions__codename__in=[permission_list[0]]).first()
            if group_module:
                request.session['url_last'] = request.path
                request.session['module'] = group_module.module
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, 'Tu perfil no cuenta con el permiso necesario para ingresar')
        return HttpResponseRedirect(self.get_last_url())


class SuperuserRequiredMixin(object):
    # Para vistas de superadministración multi-compañía (ej. gestionar
    # TODAS las compañías desde /tenant/company/). El permiso Django
    # genérico por modelo (ej. change_company) NO basta como filtro aquí:
    # el mismo codename lo tiene el grupo Administrador de CUALQUIER
    # compañía, para su propio autoservicio de "Editar Compañía" (ver
    # core/pos/views/company/views.py, que edita solo self.request.tenant.
    # company) -sin este mixin, cualquier Administrador de cualquier
    # compañía podía editar (y leer credenciales de) OTRAS compañías
    # adivinando su id en /tenant/company/update/<pk>/. Se exige
    # is_superuser explícitamente, aparte del sistema de permisos por
    # grupo, que sigue aplicando después (ver GroupPermissionMixin).
    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            messages.error(request, 'Esta sección es exclusiva del superadministrador')
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        return super().dispatch(request, *args, **kwargs)


class GroupModuleMixin(LoginRequiredMixin, object):
    redirect_field_name = settings.LOGIN_REDIRECT_URL

    def get_last_url(self):
        request = get_current_request()
        if 'url_last' in request.session:
            if request.session['url_last'] != request.path:
                return request.session['url_last']
        return settings.LOGIN_REDIRECT_URL

    def dispatch(self, request, *args, **kwargs):
        # Mismo motivo que en GroupPermissionMixin.dispatch(): revisar en
        # dispatch() para que también cubra post(), no solo get().
        if 'group' not in request.session:
            return HttpResponseRedirect(settings.LOGIN_REDIRECT_URL)
        request.session['module'] = None
        group = request.session['group']
        group_module = group.groupmodule_set.filter(module__url=request.path).first()
        if group_module:
            request.session['url_last'] = request.path
            request.session['module'] = group_module.module
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, 'Tu perfil no cuenta con el permiso necesario para ingresar')
        return HttpResponseRedirect(self.get_last_url())

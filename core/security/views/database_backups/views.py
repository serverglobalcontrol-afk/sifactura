import json
import os
import shutil
import subprocess
from datetime import datetime

from django.core.files import File
from django.db import connection
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import DeleteView, TemplateView, FormView
from django_tenants.utils import get_public_schema_name

from config import settings
from core.reports.forms import ReportForm
from core.security.mixins import GroupPermissionMixin
from core.security.models import DatabaseBackups


def get_postgresql_bin(name):
    path = shutil.which(name)
    if path:
        return path
    for version in ('17', '16', '15', '14', '13'):
        candidate = rf'C:\Program Files\PostgreSQL\{version}\bin\{name}.exe'
        if os.path.exists(candidate):
            return candidate
    return name


class DatabaseBackupsListView(GroupPermissionMixin, FormView):
    template_name = 'database_backups/list.html'
    form_class = ReportForm
    permission_required = 'view_database_backups'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                queryset = DatabaseBackups.objects.filter()
                start_date = request.POST['start_date']
                end_date = request.POST['end_date']
                if len(start_date) and len(end_date):
                    queryset = queryset.filter(date_joined__range=[start_date, end_date])
                for i in queryset:
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de respaldos de la base de datos'
        context['create_url'] = reverse_lazy('database_backups_create')
        return context


class DatabaseBackupsCreateView(GroupPermissionMixin, TemplateView):
    template_name = 'database_backups/create.html'
    success_url = reverse_lazy('database_backups_list')
    permission_required = 'add_database_backups'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                vendor = connection.vendor
                if vendor == 'sqlite':
                    data = self.create_backup_sqlite()
                elif vendor == 'postgresql':
                    data = self.create_backup_postgresql()
                else:
                    data['error'] = f'No se ha podido sacar el respaldo de la base de datos {vendor}'
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def create_backup_sqlite(self):
        file = ''
        data = {}
        try:
            db_name = connection.settings_dict['NAME']
            date_now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            name_backup = f'backup_{date_now}.db'
            script = f' sqlite3 {db_name} ".backup {name_backup}"'
            subprocess.call(script, shell=True)
            file = os.path.join(settings.BASE_DIR, name_backup)
            database_backups = DatabaseBackups()
            database_backups.user = self.request.user
            database_backups.archive.save(name_backup, File(open(file, 'rb')), save=False)
            database_backups.save()
        except Exception as e:
            data['error'] = str(e)
        finally:
            if len(file):
                os.remove(file)
        return data

    def create_backup_postgresql(self):
        file = ''
        data = {}
        try:
            db_settings = connection.settings_dict
            db_name = db_settings['NAME']
            db_host = db_settings['HOST'] or 'localhost'
            db_port = db_settings['PORT'] or '5432'
            db_user = db_settings['USER']
            db_password = db_settings['PASSWORD']
            is_public_schema = connection.schema_name == get_public_schema_name()
            date_now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            prefix = 'backup_sistema' if is_public_schema else f'backup_{connection.schema_name}'
            name_backup = f'{prefix}_{date_now}.backup'
            file = os.path.join(settings.BASE_DIR, name_backup)
            cmd = [
                get_postgresql_bin('pg_dump'),
                '-h', db_host, '-p', str(db_port), '-U', db_user,
                '-F', 'c', '-b', '-f', file,
            ]
            if not is_public_schema:
                # Un respaldo de una compañía solo debe contener su propio esquema,
                # nunca los datos de las demás compañías que comparten la misma base de datos.
                cmd += ['-n', connection.schema_name]
            cmd.append(db_name)
            env = os.environ.copy()
            if db_password:
                env['PGPASSWORD'] = db_password
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(result.stderr.strip() or 'No se pudo generar el respaldo de la base de datos')
            database_backups = DatabaseBackups()
            database_backups.user = self.request.user
            database_backups.archive.save(name_backup, File(open(file, 'rb')), save=False)
            database_backups.save()
        except Exception as e:
            data['error'] = str(e)
        finally:
            if len(file) and os.path.exists(file):
                os.remove(file)
        return data

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Respaldo de Base de Datos'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['is_public_schema'] = connection.schema_name == get_public_schema_name()
        return context


class DatabaseBackupsDeleteView(GroupPermissionMixin, DeleteView):
    model = DatabaseBackups
    template_name = 'delete.html'
    success_url = reverse_lazy('database_backups_list')
    permission_required = 'delete_database_backups'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context

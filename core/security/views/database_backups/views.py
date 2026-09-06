import json
import subprocess
from datetime import datetime
import os

from django.core.files import File
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DeleteView, TemplateView, FormView
from django_tenants.utils import get_public_schema_name

from config import settings
from core.reports.forms import ReportForm
from core.security.backups import create_postgresql_backup, restore_postgresql_backup
from core.security.mixins import GroupPermissionMixin
from core.security.models import DatabaseBackups


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
                    data = create_postgresql_backup(request.user)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Respaldo de Base de Datos'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['is_public_schema'] = connection.schema_name == get_public_schema_name()
        return context


class DatabaseBackupsRestoreView(GroupPermissionMixin, TemplateView):
    template_name = 'database_backups/restore.html'
    success_url = reverse_lazy('database_backups_list')
    permission_required = 'restore_database_backups'

    def get_object(self):
        return get_object_or_404(DatabaseBackups, pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if request.POST.get('action') == 'restore':
                backup = self.get_object()
                vendor = connection.vendor
                if vendor == 'postgresql':
                    data = restore_postgresql_backup(backup)
                else:
                    data['error'] = f'No se ha podido restaurar la base de datos {vendor}'
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['object'] = self.get_object()
        context['title'] = 'Restaurar Respaldo de Base de Datos'
        context['list_url'] = self.success_url
        context['action'] = 'restore'
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

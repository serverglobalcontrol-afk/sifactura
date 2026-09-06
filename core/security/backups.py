import os
import shutil
import subprocess
from datetime import datetime

from django.core.files import File
from django.db import connection
from django_tenants.utils import get_public_schema_name

from config import settings
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


def create_postgresql_backup(user, upload_to_drive=True):
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
        database_backups.user = user
        database_backups.archive.save(name_backup, File(open(file, 'rb')), save=False)
        database_backups.save()
        if upload_to_drive:
            _upload_to_drive_if_connected(database_backups, is_public_schema)
    except Exception as e:
        data['error'] = str(e)
    finally:
        if len(file) and os.path.exists(file):
            os.remove(file)
    return data


def restore_postgresql_backup(backup):
    data = {}
    try:
        db_settings = connection.settings_dict
        db_name = db_settings['NAME']
        db_host = db_settings['HOST'] or 'localhost'
        db_port = db_settings['PORT'] or '5432'
        db_user = db_settings['USER']
        db_password = db_settings['PASSWORD']
        is_public_schema = connection.schema_name == get_public_schema_name()
        cmd = [
            get_postgresql_bin('pg_restore'),
            '-h', db_host, '-p', str(db_port), '-U', db_user,
            '-d', db_name, '--clean', '--if-exists',
        ]
        if not is_public_schema:
            # El respaldo de una compañía solo puede restaurar su propio
            # esquema, nunca sobreescribir los datos de las demás.
            cmd += ['-n', connection.schema_name]
        cmd.append(backup.archive.path)
        env = os.environ.copy()
        if db_password:
            env['PGPASSWORD'] = db_password
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(result.stderr.strip() or 'No se pudo restaurar el respaldo de la base de datos')
    except Exception as e:
        data['error'] = str(e)
    return data


def _upload_to_drive_if_connected(database_backups, is_public_schema):
    from core.tenant import google_drive
    from core.tenant.models import Company, ElectronicInvoicingProvider

    if is_public_schema:
        target = ElectronicInvoicingProvider.objects.first()
    else:
        target = Company.objects.filter(scheme__schema_name=connection.schema_name).first()

    if not target or not target.google_drive_connected:
        return

    try:
        refresh_token = target.get_google_drive_refresh_token()
        access_token = google_drive.refresh_access_token(refresh_token)
        filename = os.path.basename(database_backups.archive.name)
        result = google_drive.upload_file(access_token, target.google_drive_folder_id, database_backups.archive.path, filename)
        database_backups.google_drive_file_id = result.get('id')
        database_backups.google_drive_link = result.get('webViewLink')
        database_backups.google_drive_upload_error = None
    except Exception as e:
        database_backups.google_drive_upload_error = str(e)[:255]
    database_backups.save()

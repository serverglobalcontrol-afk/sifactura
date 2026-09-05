from datetime import datetime

from django.db import models, connection
from django.utils.deconstruct import deconstructible


def file_upload_path(instance, filename, scheme, folder):
    current_date = datetime.now()
    if folder is None:
        folder = type(instance).__name__.lower()
    if not scheme:
        scheme = connection.schema_name
    return f'{scheme}/{folder}/{current_date.year}/{current_date.month}/{current_date.day}/{filename}'


@deconstructible
class UploadTo:
    # Antes upload_to era un método vinculado a la instancia del field
    # (self.get_upload_path). Django no puede serializar eso de forma estable
    # en las migraciones -cada corrida de makemigrations lo veía "distinto" y
    # generaba una migración de puro ruido (Alter field ... on ...) aunque
    # nada hubiera cambiado. @deconstructible hace que esta clase se guarde en
    # la migración por sus argumentos (scheme, folder), que sí son estables.
    def __init__(self, scheme=None, folder=None):
        self.scheme = scheme
        self.folder = folder

    def __call__(self, instance, filename):
        return file_upload_path(instance, filename, self.scheme, self.folder)

    def __eq__(self, other):
        return isinstance(other, UploadTo) and self.scheme == other.scheme and self.folder == other.folder


class CustomImageField(models.ImageField):
    def __init__(self, *args, scheme=None, folder=None, **kwargs):
        self.scheme = scheme
        self.folder = folder
        kwargs['upload_to'] = UploadTo(scheme, folder)
        super().__init__(*args, **kwargs)

    # Ya no se usa como upload_to (ver UploadTo arriba), pero se deja definido
    # porque migraciones ya aplicadas lo referencian por nombre
    # (core.security.fields.CustomImageField.get_upload_path) y Django necesita
    # poder importarlo al leer el historial de migraciones.
    def get_upload_path(self, instance, filename):
        return file_upload_path(instance, filename, self.scheme, self.folder)


class CustomFileField(models.FileField):
    def __init__(self, *args, scheme=None, folder=None, **kwargs):
        self.scheme = scheme
        self.folder = folder
        kwargs['upload_to'] = UploadTo(scheme, folder)
        super().__init__(*args, **kwargs)

    # Igual que en CustomImageField: se conserva solo por compatibilidad con
    # migraciones ya aplicadas que lo referencian.
    def get_upload_path(self, instance, filename):
        return file_upload_path(instance, filename, self.scheme, self.folder)

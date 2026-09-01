from datetime import datetime

from django.db import models, connection


def file_upload_path(instance, filename, scheme, folder):
    current_date = datetime.now()
    if folder is None:
        folder = type(instance).__name__.lower()
    if not scheme:
        scheme = connection.schema_name
    return f'{scheme}/{folder}/{current_date.year}/{current_date.month}/{current_date.day}/{filename}'


class CustomImageField(models.ImageField):
    def __init__(self, *args, scheme=None, folder=None, **kwargs):
        self.scheme = scheme
        self.folder = folder
        kwargs['upload_to'] = self.get_upload_path
        super().__init__(*args, **kwargs)

    def get_upload_path(self, instance, filename):
        return file_upload_path(instance, filename, self.scheme, self.folder)


class CustomFileField(models.FileField):
    def __init__(self, *args, scheme=None, folder=None, **kwargs):
        self.scheme = scheme
        self.folder = folder
        kwargs['upload_to'] = self.get_upload_path
        super().__init__(*args, **kwargs)

    def get_upload_path(self, instance, filename):
        return file_upload_path(instance, filename, self.scheme, self.folder)

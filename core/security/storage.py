import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage

from config import settings


class VersionedStaticFilesStorage(StaticFilesStorage):
    """Agrega la fecha de modificación del archivo (?v=...) a toda URL que
    genere {% static %}, en todas las plantillas, sin tener que tocarlas
    una por una. Así el navegador siempre pide una copia nueva de un
    .js/.css apenas cambia, en vez de quedarse con una versión vieja en
    caché hasta que alguien haga un refresco forzado."""

    def url(self, name):
        url = super().url(name)
        real_path = finders.find(name) if settings.DEBUG else self.path(name)
        try:
            version = int(os.path.getmtime(real_path))
        except (OSError, TypeError, ValueError):
            return url
        separator = '&' if '?' in url else '?'
        return f'{url}{separator}v={version}'

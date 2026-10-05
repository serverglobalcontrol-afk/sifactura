from django.apps import AppConfig


class ContabilidadConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.contabilidad'
    verbose_name = 'Contabilidad'

    def ready(self):
        import core.contabilidad.signals  # noqa: F401

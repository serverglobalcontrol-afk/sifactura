from django.db import models
from django.forms import model_to_dict

from config import settings
from core.security.fields import CustomImageField


class MarketingPage(models.Model):
    """Contenido editable de la página informativa pública (registro único).
    Se sirve en los dominios listados en settings.MARKETING_DOMAINS."""
    hero_title = models.CharField(max_length=150, verbose_name='Título principal')
    hero_subtitle = models.CharField(max_length=300, blank=True, default='', verbose_name='Subtítulo')
    hero_image = CustomImageField(null=True, blank=True, folder='marketing', scheme=settings.DEFAULT_SCHEMA, verbose_name='Imagen principal')
    footer_text = models.CharField(max_length=300, blank=True, default='', verbose_name='Texto del footer')
    facebook_url = models.CharField(max_length=250, blank=True, default='', verbose_name='Facebook')
    instagram_url = models.CharField(max_length=250, blank=True, default='', verbose_name='Instagram')
    twitter_url = models.CharField(max_length=250, blank=True, default='', verbose_name='X / Twitter')
    linkedin_url = models.CharField(max_length=250, blank=True, default='', verbose_name='LinkedIn')
    whatsapp_number = models.CharField(max_length=15, blank=True, default='', verbose_name='WhatsApp')
    contact_email = models.CharField(max_length=100, blank=True, default='', verbose_name='Correo de contacto')

    def __str__(self):
        return self.hero_title

    def get_hero_image(self):
        if self.hero_image:
            return f'{settings.MEDIA_URL}/{self.hero_image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def toJSON(self):
        item = model_to_dict(self)
        item['hero_image'] = self.get_hero_image()
        return item

    class Meta:
        verbose_name = 'Página Informativa'
        verbose_name_plural = 'Página Informativa'
        default_permissions = ()
        permissions = (
            ('view_marketingpage', 'Can view Página Informativa'),
            ('change_marketingpage', 'Can change Página Informativa'),
        )


class Promotion(models.Model):
    """Tarjeta de oferta/promoción mostrada en la página informativa."""
    title = models.CharField(max_length=100, verbose_name='Título')
    description = models.CharField(max_length=300, verbose_name='Descripción')
    image = CustomImageField(null=True, blank=True, folder='marketing', scheme=settings.DEFAULT_SCHEMA, verbose_name='Imagen')
    link_text = models.CharField(max_length=50, blank=True, default='', verbose_name='Texto del enlace')
    link_url = models.CharField(max_length=250, blank=True, default='', verbose_name='Enlace')
    order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    active = models.BooleanField(default=True, verbose_name='Activo')

    def __str__(self):
        return self.title

    def get_image(self):
        if self.image:
            return f'{settings.MEDIA_URL}/{self.image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def toJSON(self):
        item = model_to_dict(self)
        item['image'] = self.get_image()
        return item

    class Meta:
        verbose_name = 'Promoción'
        verbose_name_plural = 'Promociones'
        ordering = ['order', 'id']

"""Gastos e Ingresos se contabilizan por señal: todo pasa por ModelForm.save()
y Model.delete(), así que son los dos únicos orígenes donde una señal es
fiable. El resto (ventas, compras, cobros...) se engancha con llamadas
explícitas desde las vistas, porque guardan en varios pasos o borran en
masa (ver core/contabilidad/hooks.py)."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.contabilidad.hooks import sync
from core.pos.models import Expenses, Income


@receiver(post_save, sender=Expenses)
def expense_saved(sender, instance, **kwargs):
    sync('expense', instance.pk)


@receiver(post_delete, sender=Expenses)
def expense_deleted(sender, instance, **kwargs):
    sync('expense', instance.pk)


@receiver(post_save, sender=Income)
def income_saved(sender, instance, **kwargs):
    sync('income', instance.pk)


@receiver(post_delete, sender=Income)
def income_deleted(sender, instance, **kwargs):
    sync('income', instance.pk)

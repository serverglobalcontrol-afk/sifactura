import calendar
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db.models import signals
from django.dispatch import receiver

from core.pos.models import Sale, CreditNote, VOUCHER_TYPE


@receiver(signals.pre_save, sender=Sale)
def validate_invoice_plan_on_save(sender, instance, **kwargs):
    if not instance.pk:
        current_date = datetime.now().date()
        start_date = datetime(year=current_date.year, month=current_date.month, day=1).date()
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        end_date = datetime(year=current_date.year, month=current_date.month, day=last_day).date()

        if instance.company.plan.quantity:
            quantity = Sale.objects.filter(date_joined__range=[start_date, end_date], receipt__voucher_type=VOUCHER_TYPE[0][0]).count()
            if quantity >= instance.company.plan.quantity:
                raise ValidationError('Has excedido el límite de facturas permitidas por tu plan actual')

        if instance.company.plan.quantity:
            quantity = Sale.objects.filter(date_joined__range=[start_date, end_date], receipt__voucher_type=VOUCHER_TYPE[2][0]).count()
            if quantity >= instance.company.plan.quantity:
                raise ValidationError('Has excedido el límite de notas de venta permitidas por tu plan actual')


@receiver(signals.pre_save, sender=CreditNote)
def validate_credit_note_plan_on_save(sender, instance, **kwargs):
    if not instance.pk:
        current_date = datetime.now().date()
        start_date = datetime(year=current_date.year, month=current_date.month, day=1).date()
        last_day = calendar.monthrange(current_date.year, current_date.month)[1]
        end_date = datetime(year=current_date.year, month=current_date.month, day=last_day).date()

        if instance.company.plan.quantity:
            quantity = CreditNote.objects.filter(date_joined__range=[start_date, end_date]).count()
            if quantity >= instance.company.plan.quantity:
                raise ValidationError('Has excedido el límite de notas de crédito permitidas por tu plan actual')

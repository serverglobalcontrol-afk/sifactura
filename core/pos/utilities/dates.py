from datetime import datetime

from django.utils import timezone


def merge_date_with_time(day, base=None):
    """Día elegido por la persona + hora real: la de `base` si se pasa (ej. el registro original al editar) o la actual."""
    clock = timezone.localtime(base) if base else timezone.localtime()
    return timezone.make_aware(datetime.combine(day, clock.time()), timezone.get_current_timezone())


def parse_picked_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date()


def to_local(value):
    return timezone.localtime(value) if isinstance(value, datetime) and timezone.is_aware(value) else value

"""Reglas de efectivo en caja que dependen de QUIÉN está registrando."""
from core.security.models import GroupSettings, requires_cash_register


def cash_limit_applies(request):
    """La regla "no se puede pagar en efectivo más de lo que hay en caja" rige solo para el CAJERO (el
    perfil que opera una caja propia: GroupSettings.requires_cash_register). Un administrador puede pagar
    en efectivo o con otro medio sin que se le valide el efectivo disponible."""
    group = request.session.get('group')
    if group is not None:
        return GroupSettings.objects.filter(group=group, requires_cash_register=True).exists()
    return requires_cash_register(request.user)

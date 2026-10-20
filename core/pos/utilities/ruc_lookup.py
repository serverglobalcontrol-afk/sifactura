"""Consulta de RUC/cédula para autocompletar clientes y proveedores.

Primero el servicio en línea del SRI (datos al día) y, si no responde, el catálogo local `SriRuc` (cargado desde los
archivos públicos del SRI). Del catálogo también se completan provincia y cantón. Solo se devuelven datos públicos: el
teléfono, el correo y la calle los escribe el usuario y se guardan únicamente en el esquema de su empresa."""
import time

from django_tenants.utils import schema_context

from core.pos.utilities.sri import SRI
from core.tenant.models import SriRuc

# Si el servicio en línea no respondió, no se reintenta por unos minutos: así el usuario no espera el tiempo de espera en
# cada consulta mientras el SRI siga bloqueando o caído (el valor vive en cada proceso del servidor).
LIVE_TIMEOUT = 4
LIVE_RETRY_AFTER = 300
_live_down_until = 0.0

NOT_FOUND = 'No se encontró ese número en el SRI ni en el catálogo local. Verifica el número o ingresa los datos manualmente.'


def candidate_ruc(identification):
    """RUC a consultar: el de 13 dígitos tal cual y, para una cédula de 10 dígitos, cédula + '001' (RUC de persona natural)."""
    digits = ''.join(ch for ch in str(identification or '') if ch.isdigit())
    if len(digits) == 13:
        return digits
    if len(digits) == 10:
        return digits + '001'
    return None


def _title(value):
    return value.title() if value else ''


def from_catalog(ruc):
    with schema_context('public'):
        row = SriRuc.objects.filter(pk=ruc).first()
    if row is None:
        return None
    return {
        'source': 'catalog', 'ruc': row.ruc, 'business_name': row.business_name, 'trade_name': row.trade_name or '',
        'status': row.status, 'taxpayer_type': row.taxpayer_type or '', 'accounting_required': row.accounting_required,
        'province': _title(row.province), 'canton': _title(row.canton), 'catalog_date': row.catalog_date.isoformat(),
    }


def _yes_no(value):
    if value is None:
        return None
    return str(value).strip().upper() in ('SI', 'S', 'TRUE', '1')


def from_live(ruc):
    """(datos normalizados | None, error | None). `None, None` si el SRI no tuvo el dato o no se pudo consultar."""
    global _live_down_until
    if time.monotonic() < _live_down_until:
        return None, None
    data = SRI().search_ruc_in_sri(ruc, timeout=LIVE_TIMEOUT)
    if data.get('unreachable'):
        _live_down_until = time.monotonic() + LIVE_RETRY_AFTER
        return None, None
    if 'error' in data:
        return None, data['error']
    name = data.get('razonSocial')
    if not name:
        return None, None
    return {
        'source': 'sri', 'ruc': ruc, 'business_name': name, 'trade_name': '',
        'status': str(data.get('estadoContribuyenteRuc') or '').upper(), 'taxpayer_type': str(data.get('tipoContribuyente') or '').upper(),
        'accounting_required': _yes_no(data.get('obligadoLlevarContabilidad')), 'province': '', 'canton': '', 'catalog_date': None,
    }, None


STATUS_FIELDS = ('status', 'accounting_required', 'source', 'catalog_date')


def lookup_for_company(company, identification, use_live=True):
    """Igual que `lookup`, pero respetando la configuración de la empresa: si no tiene activado "mostrar el estado del
    contribuyente en el SRI", la respuesta no lleva el estado ni la obligación contable (el nombre y la provincia/cantón
    se completan siempre). `show_status` le indica a la pantalla si debe mostrar el panel."""
    result = lookup(identification, use_live=use_live)
    show = bool(getattr(company, 'show_sri_status', False))
    result['show_status'] = show
    if not show:
        for key in STATUS_FIELDS:
            result.pop(key, None)
    return result


def lookup(identification, use_live=True):
    """Datos públicos del contribuyente: {'found': True, ...} o {'error': mensaje}."""
    ruc = candidate_ruc(identification)
    if ruc is None:
        return {'error': 'Ingresa una cédula de 10 dígitos o un RUC de 13 dígitos.'}
    live, live_error = from_live(ruc) if use_live else (None, None)
    catalog = from_catalog(ruc)
    if live is None and catalog is None:
        return {'error': live_error or NOT_FOUND}
    result = dict(live or catalog)
    if live is not None and catalog is not None:
        # El servicio en línea no trae provincia/cantón ni nombre comercial: se toman del catálogo.
        for key in ('province', 'canton', 'trade_name', 'taxpayer_type', 'catalog_date'):
            if not result.get(key):
                result[key] = catalog[key]
        if result['accounting_required'] is None:
            result['accounting_required'] = catalog['accounting_required']
        if not result['status']:
            result['status'] = catalog['status']
    result['found'] = True
    result['address_hint'] = ', '.join(part for part in (result['province'], result['canton']) if part)
    return result

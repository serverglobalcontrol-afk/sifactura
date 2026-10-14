import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from core.rrhh.choices import RDEP_EMPLOYER_TYPE, RDEP_SOCIAL_SECURITY
from core.rrhh.models import RdepTaxBracket, RdepYear
from core.rrhh.services import rdep
from core.security.mixins import GroupPermissionMixin


def _decimal(value, label):
    try:
        return Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label} no es un número válido.')


class RdepSettingsView(GroupPermissionMixin, TemplateView):
    """Parámetros del RDEP por año: tabla del impuesto a la renta, canasta familiar básica y datos del empleador."""
    template_name = 'rdep/settings.html'
    permission_required = 'view_rdepyear'

    def post(self, request, *args, **kwargs):
        try:
            action = request.POST['action']
            year = int(request.POST['year'])
            if action == 'get':
                item = RdepYear.objects.filter(year=year).first()
                data = item.toJSON() if item else {'year': year, 'exists': False}
            elif action == 'suggest':
                data = rdep.SUGGESTED_YEARS.get(year)
                if data is None:
                    raise ValueError(f'No tengo una tabla sugerida para {year}. Cárgala a mano con los valores que publica el SRI.')
                data = {'basic_basket': data['basic_basket'], 'source': data['source'],
                        'brackets': [{'lower': a, 'upper': b, 'base_tax': c, 'rate': d} for a, b, c, d in data['brackets']]}
            elif action == 'save':
                group = request.session.get('group')
                if group is None or not group.permissions.filter(codename='change_rdepyear').exists():
                    raise ValueError('Tu perfil no cuenta con el permiso necesario para guardar los parámetros.')
                data = self.save(request, year)
            else:
                data = {'error': 'No ha seleccionado ninguna opción'}
        except Exception as e:
            data = {'error': str(e)}
        return HttpResponse(json.dumps(data), content_type='application/json')

    def save(self, request, year):
        if not 2006 <= year <= 2100:
            raise ValueError('El año no es válido.')
        basket = _decimal(request.POST['basic_basket'], 'La canasta familiar básica')
        if basket <= 0:
            raise ValueError('Escribe la canasta familiar básica de enero (por ejemplo 821.80): se usa para la rebaja de gastos personales.')
        employer_type = request.POST.get('employer_type')
        social_security = request.POST.get('social_security')
        if employer_type not in dict(RDEP_EMPLOYER_TYPE) or social_security not in dict(RDEP_SOCIAL_SECURITY):
            raise ValueError('Elige el tipo de empleador y el ente de seguridad social.')
        if employer_type == 'PRIVADO_MIXTO' and social_security != 'IESS':
            raise ValueError('Un empleador privado o mixto declara con el IESS.')
        rows = json.loads(request.POST['brackets'])
        parsed = []
        for number, row in enumerate(rows, start=1):
            lower = _decimal(row['lower'], f'La fracción básica de la fila {number}')
            upper = None if str(row.get('upper') or '').strip() == '' else _decimal(row['upper'], f'El exceso hasta de la fila {number}')
            base_tax = _decimal(row['base_tax'] or 0, f'El impuesto de la fila {number}')
            rate = _decimal(row['rate'] or 0, f'El porcentaje de la fila {number}')
            if lower < 0 or base_tax < 0 or not 0 <= rate <= 100:
                raise ValueError(f'La fila {number} tiene valores fuera de rango.')
            if upper is not None and upper <= lower:
                raise ValueError(f'En la fila {number} el "exceso hasta" debe ser mayor que la fracción básica.')
            parsed.append((lower, upper, base_tax, rate))
        if not parsed:
            raise ValueError('Agrega al menos una fila a la tabla del impuesto a la renta.')
        parsed.sort(key=lambda r: r[0])
        if parsed[0][0] != 0:
            raise ValueError('La primera fila de la tabla debe empezar en 0.')
        for before, after in zip(parsed, parsed[1:]):
            if before[1] is None or before[1] != after[0]:
                raise ValueError('Las filas deben ser continuas: el "exceso hasta" de una fila es la "fracción básica" de la siguiente.')
        if parsed[-1][1] is not None:
            raise ValueError('La última fila debe quedar sin "exceso hasta" (en adelante).')
        with transaction.atomic():
            item, _ = RdepYear.objects.get_or_create(year=year)
            item.basic_basket = basket
            item.employer_type, item.social_security = employer_type, social_security
            item.galapagos_index = _decimal(request.POST.get('galapagos_index') or '1', 'El índice de Galápagos')
            item.source = (request.POST.get('source') or '')[:250]
            item.updated_at = timezone.now()
            item.save()
            item.brackets.all().delete()
            RdepTaxBracket.objects.bulk_create([RdepTaxBracket(year=item, lower=l, upper=u, base_tax=b, rate=r) for l, u, b, r in parsed])
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Parámetros del RDEP'
        context['current_year'] = timezone.localdate().year
        context['years'] = list(RdepYear.objects.values_list('year', flat=True))
        context['employer_types'] = RDEP_EMPLOYER_TYPE
        context['social_securities'] = RDEP_SOCIAL_SECURITY
        context['has_suggestion'] = sorted(rdep.SUGGESTED_YEARS)
        return context

import json
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from core.rrhh.models import Employee, RdepEmployeeYear
from core.rrhh.services import rdep
from core.security.mixins import GroupPermissionMixin

MANUAL_LABELS = (
    ('expenses_housing', 'Gastos de vivienda'), ('expenses_health', 'Gastos de salud'),
    ('expenses_education', 'Gastos de educación, arte y cultura'), ('expenses_food', 'Gastos de alimentación'),
    ('expenses_clothing', 'Gastos de vestimenta'), ('expenses_tourism', 'Gastos de turismo'),
    ('other_employers_income', 'Ingresos gravados con otros empleadores'), ('other_employers_iess', 'Aporte personal al IESS con otros empleadores'),
    ('other_employers_tax', 'Impuesto retenido o asumido por otros empleadores'), ('tax_assumed', 'Impuesto asumido por esta empresa'),
    ('exoneration_disability', 'Exoneración por discapacidad'), ('exoneration_elderly', 'Exoneración por tercera edad'),
)


def _amount(value, label):
    text = str(value or '0').strip().replace(',', '.')
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f'"{label}" no es un número válido.')
    if number < 0:
        raise ValueError(f'"{label}" no puede ser negativo.')
    return number.quantize(Decimal('0.01'))


class RdepAnnexView(GroupPermissionMixin, TemplateView):
    """Anexo RDEP: el POST revisa el año y muestra el cálculo por empleado con avisos; el GET
    ?action=download entrega RDEPaaaa.zip solo si el anexo no tiene errores y cumple el esquema del SRI."""
    template_name = 'rdep/annex.html'
    permission_required = 'view_rdepemployeeyear'

    def get(self, request, *args, **kwargs):
        if request.GET.get('action') == 'download':
            return self.download(request)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            action = request.POST['action']
            year = int(request.POST['year'])
            if action == 'preview':
                data = rdep.build_year(request.tenant.company, year)[1]
            elif action == 'get_manual':
                item = RdepEmployeeYear.objects.filter(employee_id=request.POST['employee'], year=year).first()
                employee = Employee.objects.select_related('user').get(pk=request.POST['employee'])
                data = {'employee': employee.get_full_name(), 'values': {k: float(getattr(item, k)) if item else 0.0 for k, _ in MANUAL_LABELS}}
            elif action == 'save_manual':
                group = request.session.get('group')
                if group is None or not group.permissions.filter(codename='change_rdepemployeeyear').exists():
                    raise ValueError('Tu perfil no cuenta con el permiso necesario para guardar los datos anuales.')
                employee = Employee.objects.get(pk=request.POST['employee'])
                values = {k: _amount(request.POST.get(k), label) for k, label in MANUAL_LABELS}
                item, _ = RdepEmployeeYear.objects.get_or_create(employee=employee, year=year)
                for key, value in values.items():
                    setattr(item, key, value)
                item.updated_at = timezone.now()
                item.save()
                data = {}
            else:
                data = {'error': 'No ha seleccionado ninguna opción'}
        except Exception as e:
            data = {'error': str(e)}
        return HttpResponse(json.dumps(data), content_type='application/json')

    def download(self, request):
        try:
            year = int(request.GET['year'])
            data, summary = rdep.build_year(request.tenant.company, year)
            if not summary['valid']:
                raise ValueError(f'El RDEP {year} todavía tiene errores: corrígelos y vuelve a revisar antes de descargar.')
        except Exception as e:
            return HttpResponse(str(e), status=400, content_type='text/plain; charset=utf-8')
        response = HttpResponse(rdep.build_zip(year, data), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="RDEP{year}.zip"'
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Anexo RDEP (retenciones bajo relación de dependencia)'
        context['current_year'] = timezone.localdate().year
        context['manual_labels'] = MANUAL_LABELS
        return context

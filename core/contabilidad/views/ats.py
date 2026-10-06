from datetime import date

from django.http import HttpResponse
from django.views.generic import TemplateView

from core.contabilidad.mixins import AccountingEnabledMixin
from core.contabilidad.services import ats
from core.contabilidad.views.base import json_response
from core.security.mixins import GroupModuleMixin


class ATSView(AccountingEnabledMixin, GroupModuleMixin, TemplateView):
    """Anexo Transaccional Simplificado: el POST revisa los meses elegidos y
    muestra qué incluirá y qué datos faltan; el GET ?action=download entrega
    el ZIP (solo de meses sin errores)."""
    template_name = 'contabilidad/ats/index.html'

    def get(self, request, *args, **kwargs):
        if request.GET.get('action') == 'download':
            return self.download(request)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            if request.POST['action'] != 'preview':
                return json_response({'error': 'No ha seleccionado ninguna opción'})
            company = request.tenant.company
            months = ats.months_between(request.POST['start'], request.POST['end'])
            data = {'months': [ats.build_month(company, year, month)[1] for year, month in months]}
        except Exception as e:
            data = {'error': str(e)}
        return json_response(data)

    def download(self, request):
        try:
            company = request.tenant.company
            months = ats.months_between(request.GET['start'], request.GET['end'])
            files = []
            for year, month in months:
                xml, summary = ats.build_month(company, year, month)
                if not summary['valid']:
                    raise ValueError(f'El mes {summary["label"]} todavía tiene errores: corrígelos y vuelve a revisar antes de descargar.')
                files.append((summary['file'], ats.monthly_zip(year, month, xml)))
            if len(files) == 1:
                name, content = files[0]
            else:
                name = f'ATS_{months[0][0]}{months[0][1]:02d}_{months[-1][0]}{months[-1][1]:02d}.zip'
                content = ats.bundle_zip(files)
        except Exception as e:
            return HttpResponse(str(e), status=400, content_type='text/plain; charset=utf-8')
        response = HttpResponse(content, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{name}"'
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = date.today()
        # El ATS se presenta mes vencido: por defecto, el mes anterior.
        previous = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
        context['title'] = 'Anexo Transaccional Simplificado (ATS)'
        context['default_month'] = previous.strftime('%Y-%m')
        return context

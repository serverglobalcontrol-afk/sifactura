from django.views.generic import TemplateView

from core.marketing.models import MarketingPage, Promotion
from core.tenant.models import ElectronicInvoicingProvider, Plan


class MarketingHomeView(TemplateView):
    template_name = 'home/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page'] = MarketingPage.objects.first()
        context['promotions'] = Promotion.objects.filter(active=True)
        # El plan "Ilimitado" se identifica con quantity=0 y debe mostrarse
        # al final de la galería, no primero (0 ordena antes que el resto).
        plans = list(Plan.objects.all().order_by('quantity'))
        context['plans'] = [p for p in plans if p.quantity != 0] + [p for p in plans if p.quantity == 0]
        provider = ElectronicInvoicingProvider.objects.first()
        context['brand_name'] = provider.system_name if provider else 'Si-Factura'
        return context

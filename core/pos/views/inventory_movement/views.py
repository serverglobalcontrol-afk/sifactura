import json

from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from core.pos.forms import InventoryMovement, Product
from core.security.mixins import GroupPermissionMixin


class InventoryMovementListView(GroupPermissionMixin, TemplateView):
    template_name = 'inventory_movement/list.html'
    permission_required = 'view_inventorymovement'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                start_date = request.POST.get('start_date', '')
                end_date = request.POST.get('end_date', '')
                product_id = request.POST.get('product_id', '')
                queryset = InventoryMovement.objects.all().select_related('product__category', 'user')
                if start_date and end_date:
                    queryset = queryset.filter(date_joined__date__range=[start_date, end_date])
                if product_id:
                    queryset = queryset.filter(product_id=product_id)
                for i in queryset.order_by('-date_joined', '-id')[:500]:
                    data.append(i.toJSON())
            elif action == 'search_product':
                data = []
                term = request.POST.get('term', '')
                queryset = Product.objects.all().order_by('name')
                if len(term):
                    queryset = queryset.filter(name__icontains=term)[0:10]
                else:
                    queryset = queryset[0:10]
                for i in queryset:
                    data.append({'id': i.id, 'text': i.get_full_name()})
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Kardex - Movimientos de Inventario'
        context['list_url'] = reverse_lazy('inventory_movement_list')
        return context

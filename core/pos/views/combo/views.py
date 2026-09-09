import json

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, TemplateView

from core.pos.forms import Combo, ComboForm, ComboDetail, Product
from core.security.mixins import GroupPermissionMixin


class ComboListView(GroupPermissionMixin, TemplateView):
    template_name = 'combo/list.html'
    permission_required = 'view_combo'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'search':
                data = []
                for i in Combo.objects.all().order_by('name'):
                    data.append(i.toJSON())
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Listado de Combos'
        context['create_url'] = reverse_lazy('combo_create')
        return context


class ComboCreateView(GroupPermissionMixin, CreateView):
    model = Combo
    template_name = 'combo/create.html'
    form_class = ComboForm
    success_url = reverse_lazy('combo_list')
    permission_required = 'add_combo'

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'add':
                with transaction.atomic():
                    products = json.loads(request.POST['products'])
                    if not len(products):
                        raise Exception('Debe agregar al menos un producto componente al combo')
                    combo = Combo()
                    combo.code = request.POST['code']
                    combo.name = request.POST['name']
                    combo.description = request.POST.get('description', '')
                    combo.wholesale_price = float(request.POST.get('wholesale_price', 0) or 0)
                    combo.pvp = float(request.POST.get('pvp', 0) or 0)
                    combo.credit_card_price = float(request.POST.get('credit_card_price', 0) or 0)
                    combo.dscto = max(0.0, min(float(request.POST.get('dscto', 0) or 0), 100.0)) / 100
                    combo.save()
                    for i in products:
                        product = Product.objects.get(pk=i['id'])
                        cant = int(i['cant'])
                        if cant <= 0:
                            raise ValueError(f'Cantidad inválida para el componente {product.name}')
                        ComboDetail.objects.create(combo_id=combo.id, product_id=product.id, cant=cant)
                    data = combo.toJSON()
            elif action == 'search_product':
                data = []
                ids = json.loads(request.POST['ids'])
                term = request.POST['term']
                queryset = Product.objects.all().order_by('name').exclude(id__in=ids)
                if len(term):
                    queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
                queryset = queryset[0:50]
                for i in queryset:
                    item = i.toJSON()
                    # Igual que en Promotions: se muestra el stock (o "Sin
                    # inventario") en el texto del autocompletado para que el
                    # usuario sepa cuántas unidades tiene disponibles antes de
                    # elegir la cantidad requerida por combo.
                    stock_label = f'Stock: {i.stock}' if i.inventoried else 'Sin inventario'
                    item['value'] = f'{i.get_full_name()} — {stock_label}'
                    item['choose'] = False
                    data.append(item)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Nuevo registro de un Combo'
        context['list_url'] = self.success_url
        context['action'] = 'add'
        context['products'] = '[]'
        context['dscto'] = '0.00'
        return context


class ComboUpdateView(GroupPermissionMixin, UpdateView):
    model = Combo
    template_name = 'combo/create.html'
    form_class = ComboForm
    success_url = reverse_lazy('combo_list')
    permission_required = 'change_combo'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        data = {}
        action = request.POST['action']
        try:
            if action == 'edit':
                with transaction.atomic():
                    products = json.loads(request.POST['products'])
                    if not len(products):
                        raise Exception('Debe agregar al menos un producto componente al combo')
                    combo = self.object
                    combo.code = request.POST['code']
                    combo.name = request.POST['name']
                    combo.description = request.POST.get('description', '')
                    combo.wholesale_price = float(request.POST.get('wholesale_price', 0) or 0)
                    combo.pvp = float(request.POST.get('pvp', 0) or 0)
                    combo.credit_card_price = float(request.POST.get('credit_card_price', 0) or 0)
                    combo.dscto = max(0.0, min(float(request.POST.get('dscto', 0) or 0), 100.0)) / 100
                    combo.save()
                    combo.combodetail_set.all().delete()
                    for i in products:
                        product = Product.objects.get(pk=i['id'])
                        cant = int(i['cant'])
                        if cant <= 0:
                            raise ValueError(f'Cantidad inválida para el componente {product.name}')
                        ComboDetail.objects.create(combo_id=combo.id, product_id=product.id, cant=cant)
                    data = combo.toJSON()
            elif action == 'search_product':
                data = []
                ids = json.loads(request.POST['ids'])
                term = request.POST['term']
                queryset = Product.objects.all().order_by('name').exclude(id__in=ids)
                if len(term):
                    queryset = queryset.filter(Q(name__icontains=term) | Q(code__icontains=term))
                queryset = queryset[0:50]
                for i in queryset:
                    item = i.toJSON()
                    stock_label = f'Stock: {i.stock}' if i.inventoried else 'Sin inventario'
                    item['value'] = f'{i.get_full_name()} — {stock_label}'
                    item['choose'] = False
                    data.append(item)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_detproducts(self):
        data = []
        try:
            for i in self.object.combodetail_set.all():
                item = i.product.toJSON()
                item['cant'] = i.cant
                data.append(item)
        except:
            pass
        return json.dumps(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Edición de un Combo'
        context['list_url'] = self.success_url
        context['action'] = 'edit'
        context['products'] = self.get_detproducts()
        context['dscto'] = f'{float(self.object.dscto) * 100:.2f}'
        return context


class ComboDeleteView(GroupPermissionMixin, DeleteView):
    model = Combo
    template_name = 'delete.html'
    success_url = reverse_lazy('combo_list')
    permission_required = 'delete_combo'

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            self.get_object().delete()
        except Exception as e:
            data['error'] = str(e)
        return HttpResponse(json.dumps(data), content_type='application/json')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Notificación de eliminación'
        context['list_url'] = self.success_url
        return context

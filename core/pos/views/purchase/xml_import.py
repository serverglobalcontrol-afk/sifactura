import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.views.generic.base import View

from core.pos.forms import Category, Product, Provider, Purchase
from core.pos.utilities.purchase_xml_import import InvalidPurchaseXMLError, parse_supplier_invoice_xml
from core.security.mixins import GroupPermissionMixin

# Recargos por defecto sobre el precio de costo al crear un producto nuevo
# desde el XML del proveedor. Son solo un punto de partida: el precio de
# cada producto se puede editar libremente después, a mano.
WHOLESALE_PRICE_MARKUP = Decimal('1.15')
PVP_MARKUP = Decimal('1.25')
CREDIT_CARD_PRICE_MARKUP = Decimal('1.30')


def _apply_markup(cost, markup):
    return (cost * markup).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class PurchaseImportXmlView(GroupPermissionMixin, View):
    """
    Endpoints AJAX (usados desde el modal "Importar factura XML" de
    purchase/create.html) para importar el detalle de una compra a partir
    del XML que entrega el proveedor junto al PDF de su factura.

    No toca el flujo existente de creación de la compra: solo prepara filas
    con la misma forma que usa la tabla de productos de la compra manual
    ({id, code, short_name, cant, price}). El registro final de la Purchase
    se sigue haciendo con la acción 'add' de PurchaseCreateView, sin cambios.
    """
    permission_required = 'add_purchase'

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        data = {}
        try:
            if action == 'parse_xml':
                data = self.parse_xml(request)
            elif action == 'create_product_from_xml':
                data = self.create_product_from_xml(request)
            elif action == 'update_product_price':
                data = self.update_product_price(request)
            else:
                data['error'] = 'No ha seleccionado ninguna opción'
        except InvalidPurchaseXMLError as e:
            data = {'error': str(e)}
        except Exception as e:
            data = {'error': str(e)}
        return HttpResponse(json.dumps(data), content_type='application/json')

    def parse_xml(self, request):
        if 'archive' not in request.FILES:
            raise InvalidPurchaseXMLError('Debe seleccionar un archivo XML.')
        archive = request.FILES['archive']
        if not archive.name.lower().endswith('.xml'):
            raise InvalidPurchaseXMLError('El archivo debe tener extensión .xml.')

        raw_xml = archive.read()
        parsed = parse_supplier_invoice_xml(raw_xml)

        lines = []
        for line in parsed['lines']:
            product = Product.objects.filter(code__iexact=line['code']).first()
            result_line = {
                'code': line['code'],
                'description': line['description'],
                'cant': line['cant'],
                'price': float(line['price']),
                'product': None,
            }
            if product is not None:
                item = product.toJSON()
                item['value'] = product.get_full_name()
                result_line['product'] = item
            lines.append(result_line)

        info = dict(parsed['info'])
        provider = Provider.objects.filter(ruc=info['ruc']).first() if info.get('ruc') else None
        info['provider'] = provider.toJSON() if provider else None
        info['invoice_number_taken'] = bool(info.get('invoice_number')) and Purchase.objects.filter(number=info['invoice_number']).exists()

        return {
            'info': info,
            'lines': lines,
            'categories': [{'id': c.id, 'name': c.name} for c in Category.objects.all().order_by('name')],
        }

    def create_product_from_xml(self, request):
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        price_raw = request.POST.get('price', '')
        category_id = request.POST.get('category', '')

        if not code:
            raise InvalidPurchaseXMLError('El código del producto es obligatorio.')
        if not name:
            raise InvalidPurchaseXMLError('El nombre del producto es obligatorio.')
        if not category_id:
            raise InvalidPurchaseXMLError('Debe seleccionar una categoría para el nuevo producto.')

        try:
            price = Decimal(price_raw)
        except (InvalidOperation, TypeError):
            raise InvalidPurchaseXMLError('El precio de costo no es válido.')
        if price < 0:
            raise InvalidPurchaseXMLError('El precio de costo no puede ser negativo.')

        if Product.objects.filter(code__iexact=code).exists():
            raise InvalidPurchaseXMLError(f'Ya existe un producto con el código "{code}". Actualice la página e intente de nuevo.')

        try:
            category = Category.objects.get(pk=category_id)
        except (Category.DoesNotExist, ValueError, TypeError):
            raise InvalidPurchaseXMLError('La categoría seleccionada no es válida.')

        try:
            with transaction.atomic():
                product = Product()
                product.code = code
                product.name = name
                product.category = category
                product.price = price
                product.wholesale_price = _apply_markup(price, WHOLESALE_PRICE_MARKUP)
                product.pvp = _apply_markup(price, PVP_MARKUP)
                product.credit_card_price = _apply_markup(price, CREDIT_CARD_PRICE_MARKUP)
                product.inventoried = True
                product.with_tax = True
                product.stock = 0
                product.save()
        except IntegrityError:
            raise InvalidPurchaseXMLError(f'Ya existe un producto con el código "{code}".')

        item = product.toJSON()
        item['value'] = product.get_full_name()
        return item

    def update_product_price(self, request):
        product_id = request.POST.get('id', '')
        price_raw = request.POST.get('price', '')

        try:
            price = Decimal(price_raw)
        except (InvalidOperation, TypeError):
            raise InvalidPurchaseXMLError('El nuevo precio de costo no es válido.')
        if price < 0:
            raise InvalidPurchaseXMLError('El nuevo precio de costo no puede ser negativo.')

        try:
            product = Product.objects.get(pk=product_id)
        except (Product.DoesNotExist, ValueError, TypeError):
            raise InvalidPurchaseXMLError('El producto que intenta actualizar no existe.')

        product.price = price
        product.save()

        item = product.toJSON()
        item['value'] = product.get_full_name()
        return item

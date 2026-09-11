import base64
import math
import re
import smtplib
import tempfile
import time
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from xml.etree import ElementTree

import barcode
import unicodedata
from barcode import writer
from crum import get_current_request
from django.core.files import File
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import FloatField, F
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.forms import model_to_dict
from django.utils import timezone

from config import settings
from core.pos.choices import *
from core.pos.utilities import printer
from core.pos.utilities.pdf_creator import PDFCreator
from core.pos.utilities.sri import SRI
from core.security.fields import CustomImageField, CustomFileField
from core.tenant.choices import RETENTION_AGENT
from core.tenant.models import Company, ElectronicInvoicingProvider, ENVIRONMENT_TYPE
from core.user.models import User


def _current_user():
    request = get_current_request()
    return getattr(request, 'user', None) if request else None


def get_electronic_invoicing_provider_additional_info():
    """Campos de información adicional exigidos por el SRI (Resolución
    NAC-DGERCGC26-00000027, Registro Oficial 335 del 28/07/2026) para
    identificar al proveedor del sistema de facturación electrónica en
    cada comprobante emitido."""
    provider = ElectronicInvoicingProvider.objects.first()
    if not provider:
        return []
    return [
        {'name': 'Sistema', 'value': provider.system_name},
        {'name': 'RUC', 'value': provider.ruc},
        {'name': 'Web', 'value': provider.website},
    ]


class Provider(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Razón Social')
    ruc = models.CharField(max_length=13, unique=True, verbose_name='Número de RUC')
    mobile = models.CharField(max_length=10, unique=True, verbose_name='Teléfono celular')
    email = models.CharField(max_length=50, unique=True, verbose_name='Email')
    address = models.CharField(max_length=500, null=True, blank=True, verbose_name='Dirección')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.name} ({self.ruc})'

    def toJSON(self):
        item = model_to_dict(self)
        item['text'] = self.get_full_name()
        return item

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')

    def __str__(self):
        return self.name

    def toJSON(self):
        item = model_to_dict(self)
        return item

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'


class Product(models.Model):
    # Orden pensado para el formulario (fields='__all__' en ProductForm
    # sigue este orden): datos básicos, luego precios agrupados, luego
    # inventario/impuesto. No requiere migración -reordenar la declaración
    # de campos ya existentes no cambia el esquema de la BD, solo el orden
    # en que Django arma el formulario.
    # 25 y no 20: el esquema del SRI permite hasta 25 caracteres en
    # codigoPrincipal/codigoAuxiliar, y con 20 fallaba al crear un producto
    # nuevo importado de una factura XML real cuyo código tenía 21 caracteres.
    code = models.CharField(max_length=25, unique=True, verbose_name='Código')
    name = models.CharField(max_length=150, verbose_name='Nombre')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Descripción')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='Categoría')
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio de Compra')
    wholesale_price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio distribuidor')
    pvp = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio al público')
    credit_card_price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio tarjeta de crédito')
    # Por defecto marcado (todos los productos son editables en el carrito,
    # como siempre fue). Si se desmarca en un producto puntual, su precio
    # queda fijo en el carrito de Venta/Cotización -el vendedor no puede
    # editarlo a mano, solo ve el precio calculado según el tipo de precio
    # del cliente.
    manual_price = models.BooleanField(default=True, verbose_name='Precio de venta manual')
    stock_minimo = models.IntegerField(default=5, verbose_name='Stock mínimo')
    inventoried = models.BooleanField(default=True, verbose_name='¿Es inventariado?')
    with_tax = models.BooleanField(default=True, verbose_name='¿Se cobra impuesto?')
    image = CustomImageField(null=True, blank=True, verbose_name='Imagen')
    barcode = CustomImageField(folder='barcode', null=True, blank=True, verbose_name='Código de barra')
    stock = models.IntegerField(default=0)

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.name} ({self.code}) ({self.category.name})'

    def get_short_name(self):
        return f'{self.name} ({self.category.name})'

    def get_inventoried(self):
        if self.inventoried:
            return 'Inventariado'
        return 'No inventariado'

    def get_price_promotion(self):
        promotions = self.promotionsdetail_set.filter(promotion__state=True).first()
        if promotions:
            return promotions.price_final
        return 0.00

    def get_price_current(self, customer_type=CUSTOMER_TYPE[0][0], price_promotion=None):
        # price_promotion se puede pasar ya calculado (ej. desde toJSON, que
        # ya lo consulta) para no repetir la misma consulta dos veces por
        # producto en listados donde se llama a ambos -eso duplicaba una
        # consulta por producto en búsquedas con muchos resultados.
        if price_promotion is None:
            price_promotion = self.get_price_promotion()
        if price_promotion > 0:
            return float(price_promotion)

        if customer_type == CUSTOMER_TYPE[0][0]:
            return float(self.pvp)
        elif customer_type == CUSTOMER_TYPE[1][0]:
            return float(self.wholesale_price)
        elif customer_type == CUSTOMER_TYPE[2][0]:
            return float(self.credit_card_price)

        return float(self.pvp)

    def get_image(self):
        if self.image:
            return f'{settings.MEDIA_URL}/{self.image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def get_barcode(self):
        if self.barcode:
            return f'{settings.MEDIA_URL}/{self.barcode}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def get_benefit(self):
        benefit = float(self.pvp) - float(self.price)
        return round(benefit, 2)

    def is_low_stock(self):
        return self.inventoried and self.stock <= self.stock_minimo

    def generate_barcode(self):
        image_io = BytesIO()
        barcode.Gs1_128(self.code, writer=barcode.writer.ImageWriter()).write(image_io)
        # Un código con "/" (códigos de proveedor tomados de facturas XML reales
        # los traen, ej. "DS-IDS-7208HQHI-M1/XT") se interpreta como separador de
        # carpetas si se usa tal cual de nombre de archivo, creando subcarpetas
        # inesperadas en el storage. Se sanitiza solo el NOMBRE del archivo; el
        # código que se codifica en el propio código de barras no cambia.
        safe_code = re.sub(r'[^A-Za-z0-9_.-]', '_', self.code)
        filename = f'{safe_code}.png'
        self.barcode.save(filename, content=ContentFile(image_io.getvalue()), save=False)

    def toJSON(self, exclude=None):
        exclude = exclude or []
        item = model_to_dict(self, exclude=exclude)
        item['value'] = self.get_full_name()
        item['full_name'] = self.get_full_name()
        item['short_name'] = self.get_short_name()
        item['category'] = self.category.toJSON()
        if 'price' not in exclude:
            item['price'] = float(self.price)
        item['price_promotion'] = float(self.get_price_promotion())
        # item['price_current'] = float(self.get_price_current())
        item['pvp'] = float(self.pvp)
        item['wholesale_price'] = float(self.wholesale_price)
        item['credit_card_price'] = float(self.credit_card_price)
        item['image'] = self.get_image()
        item['barcode'] = self.get_barcode()
        item['low_stock'] = self.is_low_stock()
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        # Generar el código de barras implica escribir un PNG a storage; hacerlo
        # en cada guardado (incluido cada línea de venta/compra que solo cambia
        # el stock) es I/O innecesario. Solo se regenera si el producto es
        # nuevo, no tiene código de barras aún, o el código cambió.
        needs_barcode = self.pk is None or not self.barcode
        if not needs_barcode:
            needs_barcode = Product.objects.filter(pk=self.pk).exclude(code=self.code).exists()
        if needs_barcode:
            self.generate_barcode()
        super(Product, self).save()

    def register_movement(self, quantity, movement_type, reference, reason=None, user=None):
        # Punto único por donde debe pasar cualquier cambio de stock: además de
        # sumar/restar sobre el contador rápido (self.stock), deja un renglón
        # en el Kardex con el stock antes/después, para poder reconstruir por
        # qué el stock de un producto es el que es. quantity positivo = entrada,
        # negativo = salida.
        if quantity == 0:
            return None
        stock_before = self.stock
        self.stock = stock_before + quantity
        self.save()
        return InventoryMovement.objects.create(
            product=self,
            movement_type=movement_type,
            quantity=quantity,
            stock_before=stock_before,
            stock_after=self.stock,
            reference=reference,
            reason=reason,
            user=user,
        )

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        default_permissions = ()
        permissions = (
            ('view_product', 'Can view Producto'),
            ('add_product', 'Can add Producto'),
            ('change_product', 'Can change Producto'),
            ('delete_product', 'Can delete Producto'),
            ('adjust_product_stock', 'Can adjust_product_stock Producto'),
        )


class InventoryMovement(models.Model):
    MOVEMENT_TYPE = (
        ('compra', 'Compra'),
        ('venta', 'Venta'),
        ('nota_credito', 'Nota de Crédito'),
        ('ajuste', 'Ajuste Manual'),
        ('eliminacion', 'Eliminación de Comprobante'),
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='Producto')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE, verbose_name='Tipo de movimiento')
    # Positivo = entrada (sube el stock), negativo = salida (baja el stock).
    quantity = models.IntegerField(verbose_name='Cantidad')
    stock_before = models.IntegerField(verbose_name='Stock antes')
    stock_after = models.IntegerField(verbose_name='Stock después')
    reference = models.CharField(max_length=200, verbose_name='Referencia')
    reason = models.CharField(max_length=500, null=True, blank=True, verbose_name='Motivo')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Usuario')
    date_joined = models.DateTimeField(default=datetime.now, verbose_name='Fecha')

    def __str__(self):
        return f'{self.product.name} ({self.quantity:+d})'

    def get_direction(self):
        return 'Entrada' if self.quantity > 0 else 'Salida'

    def toJSON(self):
        item = model_to_dict(self, exclude=['product', 'user'])
        item['product'] = self.product.toJSON()
        item['movement_type'] = {'id': self.movement_type, 'name': self.get_movement_type_display()}
        item['direction'] = self.get_direction()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d %H:%M')
        item['user'] = self.user.names if self.user else 'Sistema'
        return item

    class Meta:
        verbose_name = 'Movimiento de Inventario'
        verbose_name_plural = 'Movimientos de Inventario (Kardex)'
        default_permissions = ()
        permissions = (
            ('view_inventorymovement', 'Can view Movimiento de Inventario'),
        )


class Purchase(models.Model):
    # 20 y no 8: al importar la factura desde el XML del proveedor se usa
    # establecimiento+puntoEmisión+secuencial (3+3+9 = 15 dígitos) para evitar
    # colisiones entre proveedores/establecimientos distintos que reutilicen
    # el mismo secuencial.
    number = models.CharField(max_length=20, unique=True, verbose_name='Número de factura')
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, verbose_name='Proveedor')
    payment_type = models.CharField(choices=PAYMENT_TYPE, max_length=50, default=PAYMENT_TYPE[0][0], verbose_name='Tipo de pago')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de registro')
    end_credit = models.DateField(default=datetime.now, verbose_name='Fecha de plazo de credito')
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    # Identificador que genera el navegador una sola vez por intento de compra.
    # Si la misma compra llega dos veces (doble clic, reintento de red), la
    # segunda petición encuentra este valor ya usado y no crea un duplicado.
    idempotency_key = models.CharField(max_length=40, null=True, blank=True, unique=True, verbose_name='Llave de idempotencia')

    def __str__(self):
        return self.provider.name

    def calculate_invoice(self):
        # Se suma a nivel de base de datos y se redondea una sola vez al final,
        # igual que Sale/CreditNote/Quotation, en vez de acumular en float línea
        # por línea (que puede desviar el total en centavos con muchas líneas).
        subtotal = self.purchasedetail_set.aggregate(result=Coalesce(Sum('subtotal'), 0.00, output_field=FloatField()))['result']
        self.subtotal = round(float(subtotal), 2)
        self.save()

    def delete(self, using=None, keep_parents=False):
        # Antes cualquier error acá (incluida una resta que dejara el stock
        # negativo) se tragaba con "except: pass" y el comprobante se borraba
        # igual, dejando el stock a medio revertir sin avisar a nadie. Ahora se
        # valida primero (sin tocar nada) y recién si todo cierra se aplica,
        # todo dentro de una transacción.
        details = list(self.purchasedetail_set.all())
        for i in details:
            if i.product.inventoried and i.product.stock - i.cant < 0:
                raise ValueError(f'No se puede eliminar: el producto {i.product.name} ya tiene menos stock ({i.product.stock}) del que esta compra ingresó ({i.cant}), probablemente porque ya se vendió parte.')
        with transaction.atomic():
            for i in details:
                i.product.register_movement(-i.cant, 'eliminacion', f'Eliminación de Compra #{self.id} ({self.number})', user=_current_user())
                i.delete()
            super(Purchase, self).delete()

    def toJSON(self):
        item = model_to_dict(self)
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_credit'] = self.end_credit.strftime('%Y-%m-%d')
        item['provider'] = self.provider.toJSON()
        item['payment_type'] = {'id': self.payment_type, 'name': self.get_payment_type_display()}
        item['subtotal'] = float(self.subtotal)
        return item

    class Meta:
        verbose_name = 'Compra'
        verbose_name_plural = 'Compras'
        default_permissions = ()
        permissions = (
            ('view_purchase', 'Can view Compra'),
            ('add_purchase', 'Can add Compra'),
            ('delete_purchase', 'Can delete Compra'),
        )


class PurchaseDetail(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def toJSON(self):
        item = model_to_dict(self, exclude=['purchase'])
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['subtotal'] = float(self.subtotal)
        return item

    class Meta:
        verbose_name = 'Detalle de Compra'
        verbose_name_plural = 'Detalle de Compras'
        default_permissions = ()


# Nombres editables por el admin para los 3 tipos de precio fijos
# (CUSTOMER_TYPE). El ORDEN sigue siendo el de CUSTOMER_TYPE -Product.
# get_price_current()/Combo.get_price_current() usan ese orden por índice
# posicional para saber qué columna de precio devolver, así que reordenar
# CUSTOMER_TYPE rompería el mapeo precio<->tipo. PriceType es solo de
# presentación: cambia cómo se MUESTRA cada tipo, nunca cuál es.
DEFAULT_PRICE_TYPE_NAMES = {
    'wholesale': 'Distribuidor',
    'retail': 'Precio de Venta Publico',
    'credit_card': 'Venta Con Tarjeta',
}
PRICE_TYPE_ORDER = ['wholesale', 'retail', 'credit_card']


class PriceType(models.Model):
    code = models.CharField(max_length=30, choices=CUSTOMER_TYPE, unique=True, verbose_name='Código')
    name = models.CharField(max_length=50, verbose_name='Nombre')

    def __str__(self):
        return self.name

    @classmethod
    def get_labels(cls):
        # Nunca falla aunque todavía no existan filas (compañías nuevas): usa
        # el nombre por defecto y lo pisa con lo que haya en la BD.
        labels = dict(DEFAULT_PRICE_TYPE_NAMES)
        for i in cls.objects.all():
            labels[i.code] = i.name
        return labels

    class Meta:
        verbose_name = 'Tipo de Precio'
        verbose_name_plural = 'Tipos de Precio'
        default_permissions = ()
        permissions = (
            ('view_price_type', 'Can view Tipo de Precio'),
            ('change_price_type', 'Can change Tipo de Precio'),
        )


class Client(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    dni = models.CharField(max_length=13, unique=True, verbose_name='Número de cedula o ruc')
    mobile = models.CharField(max_length=10, unique=True, verbose_name='Teléfono')
    birthdate = models.DateField(default=datetime.now, verbose_name='Fecha de nacimiento')
    address = models.CharField(max_length=500, verbose_name='Dirección')
    identification_type = models.CharField(max_length=30, choices=IDENTIFICATION_TYPE, default=IDENTIFICATION_TYPE[0][0], verbose_name='Tipo de identificación')
    customer_type = models.CharField(max_length=30, choices=CUSTOMER_TYPE, default=CUSTOMER_TYPE[0][0], verbose_name='Tipo de Precio de Venta')
    send_email_invoice = models.BooleanField(default=True, verbose_name='¿Enviar email de factura?')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.user.names} ({self.dni})'

    def birthdate_format(self):
        return self.birthdate.strftime('%Y-%m-%d')

    def toJSON(self):
        item = model_to_dict(self)
        item['text'] = self.get_full_name()
        item['user'] = self.user.toJSON()
        item['identification_type'] = {'id': self.identification_type, 'name': self.get_identification_type_display()}
        item['birthdate'] = self.birthdate.strftime('%Y-%m-%d')
        return item

    def delete(self, using=None, keep_parents=False):
        super(Client, self).delete()
        try:
            self.user.delete()
        except:
            pass

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'


class Receipt(models.Model):
    voucher_type = models.CharField(max_length=10, choices=VOUCHER_TYPE, verbose_name='Tipo de Comprobante')
    establishment_code = models.CharField(max_length=3, verbose_name='Código del Establecimiento Emisor')
    issuing_point_code = models.CharField(max_length=3, verbose_name='Código del Punto de Emisión')
    sequence = models.PositiveIntegerField(default=1, verbose_name='Secuencia actual')

    def __str__(self):
        return f'{self.name} - {self.establishment_code} - {self.issuing_point_code}'

    @property
    def name(self):
        return self.get_voucher_type_display()

    @property
    def is_ticket(self):
        return self.voucher_type == VOUCHER_TYPE[2][0]

    def get_name_xml(self):
        return self.remove_accents(self.name.replace(' ', '_').lower())

    def remove_accents(self, text):
        return ''.join((c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn'))

    def get_sequence(self):
        return f'{self.sequence:09d}'

    def toJSON(self):
        item = model_to_dict(self)
        item['name'] = self.name
        item['voucher_type'] = {'id': self.voucher_type, 'name': self.get_voucher_type_display()}
        return item

    class Meta:
        verbose_name = 'Comprobante'
        verbose_name_plural = 'Comprobantes'


class Sale(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Compañia')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, verbose_name='Cliente')
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, limit_choices_to={'voucher_type__in': [VOUCHER_TYPE[0][0], VOUCHER_TYPE[2][0]]}, verbose_name='Tipo de comprobante')
    voucher_number = models.CharField(max_length=9, verbose_name='Número de comprobante')
    voucher_number_full = models.CharField(max_length=20, verbose_name='Número de comprobante completo')
    employee = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Empleado')
    payment_type = models.CharField(choices=SALE_PAYMENT_TYPE, max_length=50, default=SALE_PAYMENT_TYPE[0][0], verbose_name='Tipo de pago')
    payment_method = models.CharField(choices=PAYMENT_METHOD, max_length=50, default=PAYMENT_METHOD[5][0], verbose_name='Método de pago')
    time_limit = models.IntegerField(default=31, verbose_name='Plazo')
    creation_date = models.DateTimeField(default=datetime.now, verbose_name='Fecha y hora de registro')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de registro')
    end_credit = models.DateField(default=datetime.now, verbose_name='Fecha limite de credito')
    # Transferencia
    transfer_bank = models.CharField(max_length=100, null=True, blank=True, verbose_name='Entidad bancaria')
    transfer_number = models.CharField(max_length=50, null=True, blank=True, verbose_name='Número de transferencia')
    # Tarjeta de crédito
    card_type = models.CharField(choices=CARD_TYPE, max_length=50, null=True, blank=True, verbose_name='Tipo de tarjeta')
    card_transaction_type = models.CharField(choices=CARD_TRANSACTION_TYPE, max_length=20, null=True, blank=True, verbose_name='Tipo de transacción')
    card_owner_id = models.CharField(max_length=20, null=True, blank=True, verbose_name='Cédula/RUC del propietario de la tarjeta')
    card_authorization_number = models.CharField(max_length=50, null=True, blank=True, verbose_name='Número de autorización')
    additional_info = models.JSONField(default=dict, verbose_name='Información adicional')
    observations = models.TextField(blank=True, default='', verbose_name='Observaciones')
    subtotal_12 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal')
    subtotal_0 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 0%')
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor del descuento')
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Iva')
    total_iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor de iva')
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Total a pagar')
    cash = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Efectivo recibido')
    change = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Cambio')
    environment_type = models.PositiveIntegerField(choices=ENVIRONMENT_TYPE, default=ENVIRONMENT_TYPE[0][0])
    access_code = models.CharField(max_length=49, null=True, blank=True, verbose_name='Clave de acceso')
    authorization_date = models.DateField(null=True, blank=True, verbose_name='Fecha de emisión')
    xml_authorized = CustomFileField(null=True, blank=True, verbose_name='XML Autorizado')
    pdf_authorized = CustomFileField(folder='pdf_authorized', null=True, blank=True, verbose_name='PDF Autorizado')
    create_electronic_invoice = models.BooleanField(default=True, verbose_name='Crear factura electrónica')
    status = models.CharField(max_length=50, choices=INVOICE_STATUS, default=INVOICE_STATUS[0][0], verbose_name='Estado')
    # Identificador que genera el navegador una sola vez por intento de venta.
    # Si la misma venta llega dos veces (doble clic, reintento de red), la
    # segunda petición encuentra este valor ya usado y no crea un duplicado.
    idempotency_key = models.CharField(max_length=40, null=True, blank=True, unique=True, verbose_name='Llave de idempotencia')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.voucher_number_full} / {self.client.get_full_name()})'

    def recalculate_invoice(self):
        self.calculate_detail()
        self.calculate_invoice()

    def get_iva_percent(self):
        return int(self.iva * 100)

    def get_full_subtotal(self):
        return float(self.subtotal_0) + float(self.subtotal_12)

    def get_subtotal_without_taxes(self):
        return float(self.saledetail_set.filter().aggregate(result=Coalesce(Sum('subtotal'), 0.00, output_field=FloatField()))['result'])

    def get_full_additional_info(self):
        return get_electronic_invoicing_provider_additional_info() + list(self.additional_info)

    def get_authorization_date(self):
        if self.authorization_date is None:
            return 'Pendiente de autorización'
        return self.authorization_date.strftime('%Y-%m-%d')

    def get_date_joined(self):
        return (datetime.strptime(self.date_joined, '%Y-%m-%d') if isinstance(self.date_joined, str) else self.date_joined).strftime('%Y-%m-%d')

    def get_end_credit(self):
        return (datetime.strptime(self.end_credit, '%Y-%m-%d') if isinstance(self.end_credit, str) else self.end_credit).strftime('%Y-%m-%d')

    def get_xml_authorized(self):
        if self.xml_authorized:
            return f'{settings.MEDIA_URL}/{self.xml_authorized}'
        return None

    def get_pdf_authorized(self):
        if self.pdf_authorized:
            return f'{settings.MEDIA_URL}/{self.pdf_authorized}'
        return None

    def get_voucher_number_full(self):
        return f'{self.receipt.establishment_code}-{self.receipt.issuing_point_code}-{self.voucher_number}'

    def generate_voucher_number(self, increase=True):
        if isinstance(self.receipt.sequence, str):
            self.receipt.sequence = int(self.receipt.sequence)
        number = self.receipt.sequence + 1 if increase else self.receipt.sequence
        return f'{number:09d}'

    def generate_voucher_number_full(self):
        request = get_current_request()
        if self.company_id is None:
            self.company = request.tenant.company
        if self.receipt_id is None:
            self.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[0][0], establishment_code=self.company.establishment_code, issuing_point_code=self.company.issuing_point_code)
        self.voucher_number = self.generate_voucher_number()
        return self.get_voucher_number_full()

    def generate_pdf_authorized(self):
        rv = BytesIO()
        barcode.Code128(self.access_code, writer=barcode.writer.ImageWriter()).write(rv, options={'text_distance': 3.0, 'font_size': 6})
        file = base64.b64encode(rv.getvalue()).decode("ascii")
        context = {'sale': self, 'access_code_barcode': f"data:image/png;base64,{file}"}
        pdf_file = printer.create_pdf(context=context, template_name='sale/format/invoice.html')
        with tempfile.NamedTemporaryFile(delete=True) as file_temp:
            file_temp.write(pdf_file)
            file_temp.flush()
            self.pdf_authorized.save(name=f'{self.receipt.get_name_xml()}_{self.access_code}.pdf', content=File(file_temp))

    def generate_xml(self):
        access_key = SRI().create_access_key(self)
        root = ElementTree.Element('factura', id="comprobante", version="1.0.0")
        # infoTributaria
        xml_tax_info = ElementTree.SubElement(root, 'infoTributaria')
        ElementTree.SubElement(xml_tax_info, 'ambiente').text = str(self.company.environment_type)
        ElementTree.SubElement(xml_tax_info, 'tipoEmision').text = str(self.company.emission_type)
        ElementTree.SubElement(xml_tax_info, 'razonSocial').text = self.company.business_name
        ElementTree.SubElement(xml_tax_info, 'nombreComercial').text = self.company.tradename
        ElementTree.SubElement(xml_tax_info, 'ruc').text = self.company.ruc
        ElementTree.SubElement(xml_tax_info, 'claveAcceso').text = access_key
        ElementTree.SubElement(xml_tax_info, 'codDoc').text = self.receipt.voucher_type
        ElementTree.SubElement(xml_tax_info, 'estab').text = self.receipt.establishment_code
        ElementTree.SubElement(xml_tax_info, 'ptoEmi').text = self.receipt.issuing_point_code
        ElementTree.SubElement(xml_tax_info, 'secuencial').text = self.voucher_number
        ElementTree.SubElement(xml_tax_info, 'dirMatriz').text = self.company.main_address
        if self.company.regimen_rimpe:
            ElementTree.SubElement(xml_tax_info, 'contribuyenteRimpe').text = self.company.regimen_rimpe
        if self.company.retention_agent == RETENTION_AGENT[0][0]:
            ElementTree.SubElement(xml_tax_info, 'agenteRetencion').text = '1'
        # infoFactura
        xml_info_invoice = ElementTree.SubElement(root, 'infoFactura')
        ElementTree.SubElement(xml_info_invoice, 'fechaEmision').text = datetime.now().strftime('%d/%m/%Y')
        ElementTree.SubElement(xml_info_invoice, 'dirEstablecimiento').text = self.company.establishment_address
        ElementTree.SubElement(xml_info_invoice, 'obligadoContabilidad').text = self.company.obligated_accounting
        ElementTree.SubElement(xml_info_invoice, 'tipoIdentificacionComprador').text = self.client.identification_type
        ElementTree.SubElement(xml_info_invoice, 'razonSocialComprador').text = self.client.user.names
        ElementTree.SubElement(xml_info_invoice, 'identificacionComprador').text = self.client.dni
        ElementTree.SubElement(xml_info_invoice, 'direccionComprador').text = self.client.address
        ElementTree.SubElement(xml_info_invoice, 'totalSinImpuestos').text = f'{self.get_full_subtotal():.2f}'
        ElementTree.SubElement(xml_info_invoice, 'totalDescuento').text = f'{self.total_dscto:.2f}'
        # totalConImpuestos
        xml_total_with_taxes = ElementTree.SubElement(xml_info_invoice, 'totalConImpuestos')
        # totalImpuesto
        if self.subtotal_0 != 0.0000:
            xml_total_tax_0 = ElementTree.SubElement(xml_total_with_taxes, 'totalImpuesto')
            ElementTree.SubElement(xml_total_tax_0, 'codigo').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(xml_total_tax_0, 'codigoPorcentaje').text = '0'
            ElementTree.SubElement(xml_total_tax_0, 'baseImponible').text = f'{self.subtotal_0:.2f}'
            ElementTree.SubElement(xml_total_tax_0, 'valor').text = '0.00'
        if self.subtotal_12 != 0.0000:
            xml_total_tax12 = ElementTree.SubElement(xml_total_with_taxes, 'totalImpuesto')
            ElementTree.SubElement(xml_total_tax12, 'codigo').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(xml_total_tax12, 'codigoPorcentaje').text = str(self.company.vat_percentage)
            ElementTree.SubElement(xml_total_tax12, 'baseImponible').text = f'{self.subtotal_12:.2f}'
            ElementTree.SubElement(xml_total_tax12, 'valor').text = f'{self.total_iva:.2f}'
        ElementTree.SubElement(xml_info_invoice, 'propina').text = '0.00'
        ElementTree.SubElement(xml_info_invoice, 'importeTotal').text = f'{self.total:.2f}'
        ElementTree.SubElement(xml_info_invoice, 'moneda').text = 'DOLAR'
        # pagos
        xml_payments = ElementTree.SubElement(xml_info_invoice, 'pagos')
        xml_payment = ElementTree.SubElement(xml_payments, 'pago')
        ElementTree.SubElement(xml_payment, 'formaPago').text = self.payment_method
        ElementTree.SubElement(xml_payment, 'total').text = f'{self.total:.2f}'
        ElementTree.SubElement(xml_payment, 'plazo').text = str(self.time_limit)
        ElementTree.SubElement(xml_payment, 'unidadTiempo').text = 'dias'
        # detalles
        xml_details = ElementTree.SubElement(root, 'detalles')
        for detail in self.saledetail_set.all():
            xml_detail = ElementTree.SubElement(xml_details, 'detalle')
            ElementTree.SubElement(xml_detail, 'codigoPrincipal').text = detail.product.code
            ElementTree.SubElement(xml_detail, 'descripcion').text = detail.product.name
            ElementTree.SubElement(xml_detail, 'cantidad').text = f'{detail.cant:.2f}'
            ElementTree.SubElement(xml_detail, 'precioUnitario').text = f'{detail.price:.2f}'
            ElementTree.SubElement(xml_detail, 'descuento').text = f'{detail.total_dscto:.2f}'
            ElementTree.SubElement(xml_detail, 'precioTotalSinImpuesto').text = f'{detail.total:.2f}'
            xml_taxes = ElementTree.SubElement(xml_detail, 'impuestos')
            xml_tax = ElementTree.SubElement(xml_taxes, 'impuesto')
            ElementTree.SubElement(xml_tax, 'codigo').text = str(TAX_CODES[0][0])
            if detail.product.with_tax:
                ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = str(self.company.vat_percentage)
                ElementTree.SubElement(xml_tax, 'tarifa').text = f'{detail.iva * 100:.2f}'
                ElementTree.SubElement(xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
                ElementTree.SubElement(xml_tax, 'valor').text = f'{detail.total_iva:.2f}'
            else:
                ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = "0"
                ElementTree.SubElement(xml_tax, 'tarifa').text = "0"
                ElementTree.SubElement(xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
                ElementTree.SubElement(xml_tax, 'valor').text = "0"
        # infoAdicional
        full_additional_info = self.get_full_additional_info()
        if len(full_additional_info):
            xml_additional_info = ElementTree.SubElement(root, 'infoAdicional')
            for additional_info in full_additional_info:
                ElementTree.SubElement(xml_additional_info, 'campoAdicional', nombre=additional_info['name']).text = additional_info['value']
        return ElementTree.tostring(root, xml_declaration=True, encoding='utf-8').decode('utf-8').replace("'", '"'), access_key

    def is_invoice(self):
        return self.receipt.voucher_type == VOUCHER_TYPE[0][0]

    def toJSON(self):
        item = model_to_dict(self)
        item['company'] = self.company.toJSON()
        item['client'] = self.client.toJSON()
        item['receipt'] = self.receipt.toJSON()
        item['employee'] = self.employee.toJSON()
        item['payment_type'] = {'id': self.payment_type, 'name': self.get_payment_type_display()}
        item['payment_method'] = {'id': self.payment_method, 'name': self.get_payment_method_display()}
        item['creation_date'] = self.creation_date.strftime('%Y-%m-%d %H:%M:%S')
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_credit'] = self.end_credit.strftime('%Y-%m-%d')
        item['subtotal_0'] = float(self.subtotal_0)
        item['subtotal_12'] = float(self.subtotal_12)
        item['subtotal'] = self.get_full_subtotal()
        item['total_dscto'] = float(self.total_dscto)
        item['iva'] = float(self.iva)
        item['total_iva'] = float(self.total_iva)
        item['total'] = float(self.total)
        item['cash'] = float(self.cash)
        item['change'] = float(self.change)
        item['environment_type'] = {'id': self.environment_type, 'name': self.get_environment_type_display()}
        item['authorization_date'] = '' if self.authorization_date is None else self.authorization_date.strftime('%Y-%m-%d')
        item['xml_authorized'] = self.get_xml_authorized()
        item['pdf_authorized'] = self.get_pdf_authorized()
        item['status'] = {'id': self.status, 'name': self.get_status_display()}
        return item

    def calculate_detail(self):
        for detail in self.saledetail_set.filter():
            detail.price = float(detail.price)
            detail.iva = float(self.iva)
            detail.price_with_vat = detail.price + (detail.price * detail.iva)
            detail.subtotal = detail.price * detail.cant
            detail.total_dscto = detail.subtotal * float(detail.dscto)
            detail.total_iva = (detail.subtotal - detail.total_dscto) * detail.iva
            detail.total = detail.subtotal - detail.total_dscto
            detail.save()

    def calculate_invoice(self):
        self.subtotal_0 = float(self.saledetail_set.filter(product__with_tax=False).aggregate(result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.subtotal_12 = float(self.saledetail_set.filter(product__with_tax=True).aggregate(result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        # El IVA se calcula una sola vez sobre el subtotal ya sumado, no sumando el
        # IVA de cada línea (que ya viene redondeado a 2 decimales por la base de
        # datos) — sumar valores ya redondeados puede desviar el total en centavos.
        self.total_iva = round(self.subtotal_12 * float(self.iva), 2)
        self.total_dscto = float(self.saledetail_set.filter().aggregate(result=Coalesce(Sum('total_dscto'), 0.00, output_field=FloatField()))['result'])
        self.total = float(self.get_full_subtotal()) + float(self.total_iva)
        self.save()

    def edit(self):
        super(Sale, self).save()

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.pk is None:
            self.receipt.sequence = int(self.voucher_number)
            self.receipt.save()
        super(Sale, self).save()

    def delete(self, using=None, keep_parents=False):
        with transaction.atomic():
            for i in self.saledetail_set.filter(product__inventoried=True):
                i.product.register_movement(i.cant, 'eliminacion', f'Eliminación de Venta {self.voucher_number_full}', user=_current_user())
                i.delete()
            super(Sale, self).delete()

    def generate_electronic_invoice(self):
        # El SRI rechaza cualquier factura electrónica a nombre de "CONSUMIDOR
        # FINAL" (cédula 9999999999999, sin identificación real) si supera los
        # $50; se valida antes de intentar todo el trámite (firmar, enviar,
        # autorizar), que de otro modo falla recién al final con un error del
        # SRI, sin haber avisado antes.
        if self.client.dni == '9999999999999' and float(self.total) > 50:
            return {
                'resp': False,
                'stage': VOUCHER_STAGE[0][0],
                'error': f'El SRI no permite emitir una factura electrónica a nombre de CONSUMIDOR FINAL por un valor mayor a $50,00 (total: ${self.total}). Registra los datos del cliente real (cédula/RUC) para poder facturar este monto.',
            }
        sri = SRI()
        result = sri.create_xml(self)
        if result['resp']:
            result = sri.firm_xml(instance=self, xml=result['xml'])
            if result['resp']:
                result = sri.validate_xml(instance=self, xml=result['xml'])
                if result['resp']:
                    result = sri.authorize_xml(instance=self)
                    index = 1
                    while not result['resp'] and index < 3:
                        time.sleep(1)
                        result = sri.authorize_xml(instance=self)
                        index += 1
                    if result['resp']:
                        result['print_url'] = self.get_pdf_authorized()
                        # La factura debe autorizarse y enviarse al cliente en el
                        # mismo momento, sin depender de que alguien la envíe
                        # manualmente después. Si el envío de correo falla, no
                        # se pierde la autorización ya obtenida (notify_by_email
                        # registra su propio error en VoucherErrors).
                        sri.notify_by_email(instance=self, company=self.company, client=self.client)
                    return result
        return result

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        default_permissions = ()
        permissions = (
            ('view_sale', 'Can view Venta'),
            ('add_sale', 'Can add Venta'),
            ('delete_sale', 'Can delete Venta'),
            ('view_sale_client', 'Can view_sale_client Venta'),
        )


class SaleDetail(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    price_with_vat = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def get_iva_percent(self):
        return int(self.iva * 100)

    def toJSON(self, args=None):
        item = model_to_dict(self, exclude=['sale'])
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['price_with_vat'] = float(self.price_with_vat)
        item['subtotal'] = float(self.subtotal)
        item['iva'] = float(self.subtotal)
        item['total_iva'] = float(self.subtotal)
        item['dscto'] = float(self.dscto) * 100
        item['total_dscto'] = float(self.total_dscto)
        item['total'] = float(self.total)
        if args is not None:
            item.update(args)
        return item

    class Meta:
        verbose_name = 'Detalle de Venta'
        verbose_name_plural = 'Detalle de Ventas'
        default_permissions = ()


class CtasCollect(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT)
    date_joined = models.DateField(default=datetime.now)
    end_date = models.DateField(default=datetime.now)
    debt = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    saldo = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    state = models.BooleanField(default=True)

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f"{self.sale.voucher_number_full} - {self.sale.client.user.names} ({self.sale.client.dni}) / {self.date_joined.strftime('%Y-%m-%d')} / ${f'{self.debt:.2f}'}"

    def validate_debt(self):
        saldo = self.paymentsctacollect_set.aggregate(result=Coalesce(Sum('valor'), 0.00, output_field=FloatField()))['result']
        self.saldo = float(self.debt) - float(saldo)
        self.state = self.saldo > 0.00
        self.save()

    def recalculate_details(self):
        with transaction.atomic():
            balance = float(self.debt)

            details = self.paymentsctacollect_set.order_by('date_joined', 'id')

            for detail in details:
                previous_balance = balance
                balance -= float(detail.valor)

                detail.__class__.objects.filter(pk=detail.pk).update(
                    previous_balance=previous_balance,
                    pending_balance=balance
                )

            self.saldo = balance
            self.state = balance > 0
            self.save(update_fields=['saldo', 'state'])

    def toJSON(self):
        item = model_to_dict(self)
        item['sale'] = self.sale.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        item['debt'] = float(self.debt)
        item['saldo'] = float(self.saldo)
        return item

    class Meta:
        verbose_name = 'Cuenta por cobrar'
        verbose_name_plural = 'Cuentas por cobrar'
        default_permissions = ()
        permissions = (
            ('view_ctas_collect', 'Can view Cuenta por cobrar'),
            ('add_ctas_collect', 'Can add Cuenta por cobrar'),
            ('delete_ctas_collect', 'Can delete Cuenta por cobrar'),
        )


class PaymentsCtaCollect(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    ctas_collect = models.ForeignKey(CtasCollect, on_delete=models.CASCADE, verbose_name='Cuenta por cobrar')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de registro')
    payment_type = models.CharField(choices=ALL_PAYMENT_TYPES, max_length=50, default=ALL_PAYMENT_TYPES[0][0], verbose_name='Forma de pago')
    bank_entity = models.CharField(max_length=100, null=True, blank=True, verbose_name='Entidad bancaria')
    reference_number = models.CharField(max_length=50, null=True, blank=True, verbose_name='Número de transferencia/cheque')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Detalles')
    previous_balance = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Saldo anterior')
    pending_balance = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Saldo pendiente')
    valor = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor')

    def __str__(self):
        return str(self.ctas_collect.id)

    def formatted_date_joined(self):
        return self.date_joined.strftime('%Y-%m-%d')

    def toJSON(self):
        item = model_to_dict(self, exclude=['ctas_collect'])
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['valor'] = float(self.valor)
        item['previous_balance'] = float(self.previous_balance)
        item['pending_balance'] = float(self.pending_balance)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(PaymentsCtaCollect, self).save()

    class Meta:
        verbose_name = 'Pago Cuenta por cobrar'
        verbose_name_plural = 'Pagos Cuentas por cobrar'
        default_permissions = ()


class DebtsPay(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT)
    date_joined = models.DateField(default=datetime.now)
    end_date = models.DateField(default=datetime.now)
    debt = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    saldo = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    state = models.BooleanField(default=True)

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f"{self.purchase.provider.name} ({self.purchase.number}) / {self.date_joined.strftime('%Y-%m-%d')} / ${f'{self.debt:.2f}'}"

    def validate_debt(self):
        saldo = self.paymentsdebtspay_set.aggregate(result=Coalesce(Sum('valor'), 0.00, output_field=FloatField()))['result']
        self.saldo = float(self.debt) - float(saldo)
        self.state = self.saldo > 0.00
        self.save()

    def toJSON(self):
        item = model_to_dict(self)
        item['purchase'] = self.purchase.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        item['debt'] = float(self.debt)
        item['saldo'] = float(self.saldo)
        return item

    class Meta:
        verbose_name = 'Cuenta por pagar'
        verbose_name_plural = 'Cuentas por pagar'
        default_permissions = ()
        permissions = (
            ('view_debts_pay', 'Can view Cuenta por pagar'),
            ('add_debts_pay', 'Can add Cuenta por pagar'),
            ('delete_debts_pay', 'Can delete Cuenta por pagar'),
        )


class PaymentsDebtsPay(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    debts_pay = models.ForeignKey(DebtsPay, on_delete=models.CASCADE, verbose_name='Cuenta por pagar')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de registro')
    payment_type = models.CharField(choices=ALL_PAYMENT_TYPES, max_length=50, default=ALL_PAYMENT_TYPES[0][0], verbose_name='Forma de pago')
    bank_entity = models.CharField(max_length=100, null=True, blank=True, verbose_name='Entidad bancaria')
    reference_number = models.CharField(max_length=50, null=True, blank=True, verbose_name='Número de transferencia/cheque')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Detalles')
    valor = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor')

    def __str__(self):
        return str(self.debts_pay.id)

    def formatted_date_joined(self):
        return self.date_joined.strftime('%Y-%m-%d')

    def toJSON(self):
        item = model_to_dict(self, exclude=['debts_pay'])
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['valor'] = float(self.valor)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(PaymentsDebtsPay, self).save()

    class Meta:
        verbose_name = 'Det. Cuenta por pagar'
        verbose_name_plural = 'Det. Cuentas por pagar'
        default_permissions = ()


class TypeExpense(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')

    def __str__(self):
        return self.name

    def toJSON(self):
        item = model_to_dict(self)
        return item

    class Meta:
        verbose_name = 'Tipo de Gasto'
        verbose_name_plural = 'Tipos de Gastos'
        default_permissions = ()
        permissions = (
            ('view_type_expense', 'Can view Tipo de Gasto'),
            ('add_type_expense', 'Can add Tipo de Gasto'),
            ('change_type_expense', 'Can change Tipo de Gasto'),
            ('delete_type_expense', 'Can delete Tipo de Gasto'),
        )


class Expenses(models.Model):
    type_expense = models.ForeignKey(TypeExpense, on_delete=models.PROTECT, verbose_name='Tipo de Gasto')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Descripción')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de Registro')
    valor = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor')

    def __str__(self):
        return self.description

    def toJSON(self):
        item = model_to_dict(self)
        item['type_expense'] = self.type_expense.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['valor'] = float(self.valor)
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(Expenses, self).save()

    class Meta:
        verbose_name = 'Gasto'
        verbose_name_plural = 'Gastos'


class Promotions(models.Model):
    start_date = models.DateField(default=datetime.now)
    end_date = models.DateField(default=datetime.now)
    state = models.BooleanField(default=True)

    def __str__(self):
        return str(self.id)

    def toJSON(self):
        item = model_to_dict(self)
        item['start_date'] = self.start_date.strftime('%Y-%m-%d')
        item['end_date'] = self.end_date.strftime('%Y-%m-%d')
        return item

    class Meta:
        verbose_name = 'Promoción'
        verbose_name_plural = 'Promociones'


class PromotionsDetail(models.Model):
    promotion = models.ForeignKey(Promotions, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    price_current = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    price_final = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def get_dscto_real(self):
        total_dscto = float(self.price_current) * float(self.dscto)
        n = 2
        return math.floor(total_dscto * 10 ** n) / 10 ** n

    def toJSON(self):
        item = model_to_dict(self, exclude=['promotion'])
        item['product'] = self.product.toJSON()
        item['price_current'] = float(self.price_current)
        item['dscto'] = float(self.dscto)
        item['total_dscto'] = float(self.total_dscto)
        item['price_final'] = float(self.price_final)
        return item

    class Meta:
        verbose_name = 'Detalle Promoción'
        verbose_name_plural = 'Detalle de Promociones'
        default_permissions = ()


class Combo(models.Model):
    # Un Combo es un producto "virtual" armado a partir de otros productos ya
    # existentes (ComboDetail). No tiene stock propio: al venderse, se
    # descuenta el stock de CADA producto componente (ver
    # SaleCreateView.post action 'add' en core/pos/views/sale/views.py), como
    # si esos productos se hubieran vendido sueltos. Por eso este modelo NO
    # tiene campo `stock` -su disponibilidad depende de get_available_stock().
    code = models.CharField(max_length=25, unique=True, verbose_name='Código')
    name = models.CharField(max_length=150, verbose_name='Nombre')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Descripción')
    # Precios de venta del combo, editables directamente igual que en
    # Product -no se derivan de la suma de los componentes. La suma de los
    # componentes se sigue mostrando en el formulario como referencia (para
    # ayudar a decidir el precio), pero el precio real que se cobra en
    # ventas/cotizaciones es el que se fija aquí.
    wholesale_price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio distribuidor')
    pvp = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio al público')
    credit_card_price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Precio tarjeta de crédito')
    # Descuento adicional opcional sobre el precio de venta fijado arriba,
    # como fracción 0-1, igual que PromotionsDetail.dscto (ej. para una
    # promoción temporal del combo).
    dscto = models.DecimalField(max_digits=9, decimal_places=4, default=0.00, verbose_name='Descuento')
    active = models.BooleanField(default=True, verbose_name='¿Está activo?')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.name} ({self.code})'

    def get_available_stock(self):
        # Disponibilidad del combo = la menor cantidad de combos que se
        # pueden armar según el stock de sus componentes inventariados
        # (stock_componente // cantidad_requerida). Si ningún componente se
        # inventaría (todos son servicios, por ejemplo), no hay límite y se
        # devuelve None.
        stocks = []
        for detail in self.combodetail_set.select_related('product').all():
            if detail.product.inventoried and detail.cant > 0:
                stocks.append(detail.product.stock // detail.cant)
        if not stocks:
            return None
        return min(stocks)

    def get_components_cost(self, customer_type=CUSTOMER_TYPE[0][0]):
        # Suma referencial de lo que costaría comprar los componentes por
        # separado, al precio vigente de cada uno. Solo informativo, para
        # ayudar a fijar el precio de venta del combo -no interviene en
        # get_price_current().
        total = 0.00
        for detail in self.combodetail_set.select_related('product').all():
            total += detail.product.get_price_current(customer_type) * detail.cant
        return round(float(total), 2)

    def get_price_current(self, customer_type=CUSTOMER_TYPE[0][0]):
        if customer_type == CUSTOMER_TYPE[0][0]:
            return float(self.pvp)
        elif customer_type == CUSTOMER_TYPE[1][0]:
            return float(self.wholesale_price)
        elif customer_type == CUSTOMER_TYPE[2][0]:
            return float(self.credit_card_price)
        return float(self.pvp)

    def get_total_dscto(self, customer_type=CUSTOMER_TYPE[0][0]):
        total_dscto = self.get_price_current(customer_type) * float(self.dscto)
        n = 2
        return math.floor(total_dscto * 10 ** n) / 10 ** n

    def get_price_final(self, customer_type=CUSTOMER_TYPE[0][0]):
        return round(self.get_price_current(customer_type) - self.get_total_dscto(customer_type), 2)

    def toJSON(self):
        item = model_to_dict(self)
        item['value'] = self.get_full_name()
        item['full_name'] = self.get_full_name()
        item['wholesale_price'] = float(self.wholesale_price)
        item['pvp'] = float(self.pvp)
        item['credit_card_price'] = float(self.credit_card_price)
        item['dscto'] = float(self.dscto) * 100
        item['price_current'] = self.get_price_current()
        item['total_dscto'] = self.get_total_dscto()
        item['price_final'] = self.get_price_final()
        item['components_cost'] = self.get_components_cost()
        item['available_stock'] = self.get_available_stock()
        item['components'] = [i.toJSON() for i in self.combodetail_set.select_related('product').all()]
        return item

    class Meta:
        verbose_name = 'Combo'
        verbose_name_plural = 'Combos'
        default_permissions = ()
        permissions = (
            ('view_combo', 'Can view Combo'),
            ('add_combo', 'Can add Combo'),
            ('change_combo', 'Can change Combo'),
            ('delete_combo', 'Can delete Combo'),
        )


class ComboDetail(models.Model):
    combo = models.ForeignKey(Combo, on_delete=models.CASCADE, verbose_name='Combo')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, verbose_name='Producto')
    cant = models.PositiveIntegerField(default=1, verbose_name='Cantidad')

    def __str__(self):
        return f'{self.product.name} x{self.cant}'

    def toJSON(self):
        item = model_to_dict(self, exclude=['combo'])
        item['product'] = self.product.toJSON()
        return item

    class Meta:
        verbose_name = 'Detalle Combo'
        verbose_name_plural = 'Detalle de Combos'
        default_permissions = ()


class VoucherErrors(models.Model):
    date_joined = models.DateField(default=datetime.now)
    datetime_joined = models.DateTimeField(default=datetime.now)
    environment_type = models.PositiveIntegerField(choices=ENVIRONMENT_TYPE, default=ENVIRONMENT_TYPE[0][0])
    reference = models.CharField(max_length=20)
    receipt = models.ForeignKey(Receipt, on_delete=models.CASCADE)
    stage = models.CharField(max_length=20, choices=VOUCHER_STAGE, default=VOUCHER_STAGE[0][0])
    errors = models.JSONField(default=dict)

    def __str__(self):
        return self.stage

    def toJSON(self):
        item = model_to_dict(self)
        item['receipt'] = self.receipt.toJSON()
        item['environment_type'] = {'id': self.environment_type, 'name': self.get_environment_type_display()}
        item['stage'] = {'id': self.stage, 'name': self.get_stage_display()}
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['datetime_joined'] = self.datetime_joined.strftime('%Y-%m-%d %H:%M')
        return item

    class Meta:
        verbose_name = 'Errores del Comprobante'
        verbose_name_plural = 'Errores de los Comprobantes'
        default_permissions = ()
        permissions = (
            ('view_voucher_errors', 'Can view Errores del Comprobante'),
            ('delete_voucher_errors', 'Can delete Errores del Comprobante'),
        )


class CreditNote(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Compañia')
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, verbose_name='Venta')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de registro')
    motive = models.CharField(max_length=300, null=True, blank=True, verbose_name='Motivo')
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, verbose_name='Tipo de comprobante')
    voucher_number = models.CharField(max_length=9, verbose_name='Número de comprobante')
    voucher_number_full = models.CharField(max_length=20, verbose_name='Número de comprobante completo')
    subtotal_12 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal')
    subtotal_0 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 0%')
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor del descuento')
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Iva')
    total_iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor de iva')
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Total a pagar')
    environment_type = models.PositiveIntegerField(choices=ENVIRONMENT_TYPE, default=ENVIRONMENT_TYPE[0][0])
    access_code = models.CharField(max_length=49, null=True, blank=True, verbose_name='Clave de acceso')
    authorization_date = models.DateTimeField(null=True, blank=True, verbose_name='Fecha de autorización')
    xml_authorized = CustomFileField(null=True, blank=True, verbose_name='XML Autorizado')
    pdf_authorized = CustomFileField(upload_to='pdf_authorized', verbose_name='PDF Autorizado')
    create_electronic_invoice = models.BooleanField(default=True, verbose_name='Crear factura electrónica')
    status = models.CharField(max_length=50, choices=INVOICE_STATUS, default=INVOICE_STATUS[0][0], verbose_name='Estado')
    # Identificador que genera el navegador una sola vez por intento de nota de
    # crédito. Si la misma nota de crédito llega dos veces (doble clic, reintento
    # de red), la segunda petición encuentra este valor ya usado y no crea un duplicado.
    idempotency_key = models.CharField(max_length=40, null=True, blank=True, unique=True, verbose_name='Llave de idempotencia')

    def __str__(self):
        return self.motive

    def get_iva_percent(self):
        return int(self.iva * 100)

    def get_full_subtotal(self):
        return float(self.subtotal_0) + float(self.subtotal_12)

    def get_subtotal_without_taxes(self):
        return float(self.creditnotedetail_set.filter().aggregate(result=Coalesce(Sum('subtotal'), 0.00, output_field=FloatField()))['result'])

    def get_authorization_date(self):
        if self.authorization_date is None:
            return 'Pendiente de autorización'
        return self.authorization_date.strftime('%Y-%m-%d %H:%M:%S')

    def get_date_joined(self):
        return (datetime.strptime(self.date_joined, '%Y-%m-%d') if isinstance(self.date_joined, str) else self.date_joined).strftime('%Y-%m-%d')

    def get_xml_authorized(self):
        if self.xml_authorized:
            return f'{settings.MEDIA_URL}/{self.xml_authorized}'
        return None

    def get_pdf_authorized(self):
        if self.pdf_authorized:
            return f'{settings.MEDIA_URL}/{self.pdf_authorized}'
        return None

    def get_voucher_number_full(self):
        return f'{self.receipt.establishment_code}-{self.receipt.issuing_point_code}-{self.voucher_number}'

    def generate_voucher_number(self):
        number = int(self.receipt.get_sequence()) + 1
        return f'{number:09d}'

    def generate_voucher_number_full(self):
        request = get_current_request()
        self.company = request.tenant.company
        self.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[1][0], establishment_code=self.company.establishment_code, issuing_point_code=self.company.issuing_point_code)
        self.voucher_number = self.generate_voucher_number()
        return self.get_voucher_number_full()

    def generate_pdf_authorized(self):
        rv = BytesIO()
        barcode.Code128(self.access_code, writer=barcode.writer.ImageWriter()).write(rv, options={'text_distance': 3.0, 'font_size': 6})
        file = base64.b64encode(rv.getvalue()).decode("ascii")
        context = {'credit_note': self, 'access_code_barcode': f"data:image/png;base64,{file}"}
        pdf_file = printer.create_pdf(context=context, template_name='credit_note/format/invoice.html')
        with tempfile.NamedTemporaryFile(delete=True) as file_temp:
            file_temp.write(pdf_file)
            file_temp.flush()
            self.pdf_authorized.save(name=f'{self.receipt.get_name_xml()}_{self.access_code}.pdf', content=File(file_temp))

    def generate_xml(self):
        access_key = SRI().create_access_key(self)
        root = ElementTree.Element('notaCredito', id="comprobante", version="1.1.0")
        # infoTributaria
        xml_tax_info = ElementTree.SubElement(root, 'infoTributaria')
        ElementTree.SubElement(xml_tax_info, 'ambiente').text = str(self.company.environment_type)
        ElementTree.SubElement(xml_tax_info, 'tipoEmision').text = str(self.company.emission_type)
        ElementTree.SubElement(xml_tax_info, 'razonSocial').text = self.company.business_name
        ElementTree.SubElement(xml_tax_info, 'nombreComercial').text = self.company.tradename
        ElementTree.SubElement(xml_tax_info, 'ruc').text = self.company.ruc
        ElementTree.SubElement(xml_tax_info, 'claveAcceso').text = access_key
        ElementTree.SubElement(xml_tax_info, 'codDoc').text = self.receipt.voucher_type
        ElementTree.SubElement(xml_tax_info, 'estab').text = self.receipt.establishment_code
        ElementTree.SubElement(xml_tax_info, 'ptoEmi').text = self.receipt.issuing_point_code
        ElementTree.SubElement(xml_tax_info, 'secuencial').text = self.voucher_number
        ElementTree.SubElement(xml_tax_info, 'dirMatriz').text = self.company.main_address
        if self.company.regimen_rimpe:
            ElementTree.SubElement(xml_tax_info, 'contribuyenteRimpe').text = self.company.regimen_rimpe
        if self.company.retention_agent == RETENTION_AGENT[0][0]:
            ElementTree.SubElement(xml_tax_info, 'agenteRetencion').text = '1'
        # infoNotaCredito
        xml_info_invoice = ElementTree.SubElement(root, 'infoNotaCredito')
        ElementTree.SubElement(xml_info_invoice, 'fechaEmision').text = datetime.now().strftime('%d/%m/%Y')
        ElementTree.SubElement(xml_info_invoice, 'dirEstablecimiento').text = self.company.establishment_address
        ElementTree.SubElement(xml_info_invoice, 'tipoIdentificacionComprador').text = self.sale.client.identification_type
        ElementTree.SubElement(xml_info_invoice, 'razonSocialComprador').text = self.sale.client.user.names
        ElementTree.SubElement(xml_info_invoice, 'identificacionComprador').text = self.sale.client.dni
        if not self.company.special_taxpayer == '000':
            ElementTree.SubElement(xml_info_invoice, 'contribuyenteEspecial').text = self.company.special_taxpayer
        ElementTree.SubElement(xml_info_invoice, 'obligadoContabilidad').text = self.company.obligated_accounting
        ElementTree.SubElement(xml_info_invoice, 'rise').text = 'Contribuyente Régimen Simplificado RISE'
        ElementTree.SubElement(xml_info_invoice, 'codDocModificado').text = self.sale.receipt.voucher_type
        ElementTree.SubElement(xml_info_invoice, 'numDocModificado').text = self.sale.voucher_number_full
        ElementTree.SubElement(xml_info_invoice, 'fechaEmisionDocSustento').text = self.sale.date_joined.strftime('%d/%m/%Y')
        ElementTree.SubElement(xml_info_invoice, 'totalSinImpuestos').text = f'{self.get_full_subtotal():.2f}'
        ElementTree.SubElement(xml_info_invoice, 'valorModificacion').text = f'{self.total:.2f}'
        ElementTree.SubElement(xml_info_invoice, 'moneda').text = 'DOLAR'
        # totalConImpuestos
        xml_total_with_taxes = ElementTree.SubElement(xml_info_invoice, 'totalConImpuestos')
        # totalImpuesto
        if self.subtotal_0 != 0.0000:
            xml_total_tax = ElementTree.SubElement(xml_total_with_taxes, 'totalImpuesto')
            ElementTree.SubElement(xml_total_tax, 'codigo').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(xml_total_tax, 'codigoPorcentaje').text = '0'
            ElementTree.SubElement(xml_total_tax, 'baseImponible').text = f'{self.subtotal_0:.2f}'
            ElementTree.SubElement(xml_total_tax, 'valor').text = f'{0:.2f}'
        if self.subtotal_12 != 0.0000:
            xml_total_tax2 = ElementTree.SubElement(xml_total_with_taxes, 'totalImpuesto')
            ElementTree.SubElement(xml_total_tax2, 'codigo').text = str(TAX_CODES[0][0])
            ElementTree.SubElement(xml_total_tax2, 'codigoPorcentaje').text = str(self.company.vat_percentage)
            ElementTree.SubElement(xml_total_tax2, 'baseImponible').text = f'{self.subtotal_12:.2f}'
            ElementTree.SubElement(xml_total_tax2, 'valor').text = f'{self.total_iva:.2f}'
        ElementTree.SubElement(xml_info_invoice, 'motivo').text = self.motive
        # detalles
        xml_details = ElementTree.SubElement(root, 'detalles')
        for detail in self.creditnotedetail_set.all():
            xml_detail = ElementTree.SubElement(xml_details, 'detalle')
            ElementTree.SubElement(xml_detail, 'codigoInterno').text = detail.product.code
            ElementTree.SubElement(xml_detail, 'descripcion').text = detail.product.name
            ElementTree.SubElement(xml_detail, 'cantidad').text = f'{detail.cant:.2f}'
            ElementTree.SubElement(xml_detail, 'precioUnitario').text = f'{detail.price:.2f}'
            ElementTree.SubElement(xml_detail, 'descuento').text = f'{detail.total_dscto:.2f}'
            ElementTree.SubElement(xml_detail, 'precioTotalSinImpuesto').text = f'{detail.total:.2f}'
            xml_taxes = ElementTree.SubElement(xml_detail, 'impuestos')
            xml_tax = ElementTree.SubElement(xml_taxes, 'impuesto')
            ElementTree.SubElement(xml_tax, 'codigo').text = str(TAX_CODES[0][0])
            if detail.product.with_tax:
                ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = str(self.company.vat_percentage)
                ElementTree.SubElement(xml_tax, 'tarifa').text = f'{detail.iva * 100:.2f}'
                ElementTree.SubElement(xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
                ElementTree.SubElement(xml_tax, 'valor').text = f'{detail.total_iva:.2f}'
            else:
                ElementTree.SubElement(xml_tax, 'codigoPorcentaje').text = "0"
                ElementTree.SubElement(xml_tax, 'tarifa').text = "0"
                ElementTree.SubElement(xml_tax, 'baseImponible').text = f'{detail.total:.2f}'
                ElementTree.SubElement(xml_tax, 'valor').text = "0"
        # infoAdicional
        xml_additional_info = ElementTree.SubElement(root, 'infoAdicional')
        ElementTree.SubElement(xml_additional_info, 'campoAdicional', nombre='dirCliente').text = self.sale.client.address
        ElementTree.SubElement(xml_additional_info, 'campoAdicional', nombre='telfCliente').text = self.sale.client.mobile
        ElementTree.SubElement(xml_additional_info, 'campoAdicional', nombre='Observacion').text = f'NOTA_CREDITO # {self.voucher_number}'
        for additional_info in get_electronic_invoicing_provider_additional_info():
            ElementTree.SubElement(xml_additional_info, 'campoAdicional', nombre=additional_info['name']).text = additional_info['value']
        return ElementTree.tostring(root, xml_declaration=True, encoding='UTF-8').decode('UTF-8').replace("'", '"'), access_key

    def toJSON(self):
        item = model_to_dict(self)
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['sale'] = self.sale.toJSON()
        item['company'] = self.company.toJSON()
        item['receipt'] = self.receipt.toJSON()
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['subtotal_12'] = float(self.subtotal_12)
        item['subtotal_0'] = float(self.subtotal_0)
        item['subtotal'] = self.get_full_subtotal()
        item['total_dscto'] = float(self.total_dscto)
        item['iva'] = float(self.iva)
        item['total_iva'] = float(self.total_iva)
        item['total'] = float(self.total)
        item['environment_type'] = {'id': self.environment_type, 'name': self.get_environment_type_display()}
        item['invoice'] = self.get_voucher_number_full()
        item['authorization_date'] = '' if self.authorization_date is None else self.authorization_date.strftime('%Y-%m-%d')
        item['xml_authorized'] = self.get_xml_authorized()
        item['pdf_authorized'] = self.get_pdf_authorized()
        item['status'] = {'id': self.status, 'name': self.get_status_display()}
        return item

    def generate_electronic_invoice(self):
        sri = SRI()
        result = sri.create_xml(self)
        if result['resp']:
            result = sri.firm_xml(instance=self, xml=result['xml'])
            if result['resp']:
                result = sri.validate_xml(instance=self, xml=result['xml'])
                if result['resp']:
                    return sri.authorize_xml(instance=self)
        return result

    def calculate_detail(self):
        for detail in self.creditnotedetail_set.filter():
            detail.price = float(detail.price)
            detail.iva = float(self.iva)
            detail.price_with_vat = detail.price + (detail.price * detail.iva)
            detail.subtotal = detail.price * detail.cant
            detail.total_dscto = detail.subtotal * float(detail.dscto)
            detail.total_iva = (detail.subtotal - detail.total_dscto) * detail.iva
            detail.total = detail.subtotal - detail.total_dscto
            detail.save()

    def calculate_invoice(self):
        self.subtotal_0 = float(self.creditnotedetail_set.filter(product__with_tax=False).aggregate(result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.subtotal_12 = float(self.creditnotedetail_set.filter(product__with_tax=True).aggregate(result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        # El IVA se calcula una sola vez sobre el subtotal ya sumado, no sumando el
        # IVA de cada línea (que ya viene redondeado a 2 decimales por la base de
        # datos) — sumar valores ya redondeados puede desviar el total en centavos.
        self.total_iva = round(self.subtotal_12 * float(self.iva), 2)
        self.total_dscto = float(self.creditnotedetail_set.filter().aggregate(result=Coalesce(Sum('total_dscto'), 0.00, output_field=FloatField()))['result'])
        self.total = float(self.get_full_subtotal()) + float(self.total_iva)
        self.save()

    def edit(self):
        super(CreditNote, self).save()

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.motive is None:
            self.motive = 'Sin detalles'
        if self.pk is None:
            self.receipt.sequence = int(self.voucher_number)
            self.receipt.save()
        super(CreditNote, self).save()

    def delete(self, using=None, keep_parents=False):
        # Crear una nota de crédito SUMA stock (es una devolución); al eliminarla
        # hay que revertir esa suma, no repetirla. Antes decía "+=" igual que
        # Sale.delete(), copiado sin ajustar el signo, y cada eliminación de nota
        # de crédito inflaba el stock de nuevo en vez de revertirlo.
        details = list(self.creditnotedetail_set.filter(product__inventoried=True))
        for i in details:
            if i.product.stock - i.cant < 0:
                raise ValueError(f'No se puede eliminar: el producto {i.product.name} ya tiene menos stock ({i.product.stock}) del que esta nota de crédito devolvió ({i.cant}).')
        with transaction.atomic():
            for i in details:
                i.product.register_movement(-i.cant, 'eliminacion', f'Eliminación de Nota de Crédito {self.voucher_number_full}', user=_current_user())
                i.delete()
            super(CreditNote, self).delete()

    class Meta:
        verbose_name = 'Nota de Credito'
        verbose_name_plural = 'Notas de Credito'
        default_permissions = ()
        permissions = (
            ('view_credit_note', 'Can view Nota de Credito'),
            ('add_credit_note', 'Can add Nota de Credito'),
            ('delete_credit_note', 'Can delete Nota de Credito'),
            ('view_credit_note_client', 'Can view_credit_note_client Nota de Credito'),
        )


class CreditNoteDetail(models.Model):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.CASCADE)
    sale_detail = models.ForeignKey(SaleDetail, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, blank=True, null=True, on_delete=models.PROTECT)
    date_joined = models.DateField(default=datetime.now)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    price_with_vat = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.product.name

    def toJSON(self):
        item = model_to_dict(self)
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['sale_detail'] = self.sale_detail.toJSON()
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['price_with_vat'] = float(self.price_with_vat)
        item['subtotal'] = float(self.subtotal)
        item['iva'] = float(self.subtotal)
        item['total_iva'] = float(self.subtotal)
        item['dscto'] = float(self.dscto)
        item['total_dscto'] = float(self.total_dscto)
        item['total'] = float(self.total)
        return item

    class Meta:
        verbose_name = 'Detalle Devolución Ventas'
        verbose_name_plural = 'Detalle Devoluciones Ventas'
        default_permissions = ()


class Quotation(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name='Compañia')
    client = models.ForeignKey(Client, on_delete=models.PROTECT, verbose_name='Cliente')
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, null=True, blank=True, limit_choices_to={'voucher_type': VOUCHER_TYPE[3][0]}, verbose_name='Tipo de comprobante')
    voucher_number = models.CharField(max_length=9, blank=True, default='', verbose_name='Número de comprobante')
    voucher_number_full = models.CharField(max_length=20, blank=True, default='', verbose_name='Número de comprobante completo')
    employee = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='Empleado')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de elaboración')
    validity_days = models.PositiveIntegerField(default=15, verbose_name='Días de validez')
    observations = models.TextField(blank=True, default='', verbose_name='Observaciones')
    subtotal_12 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal')
    subtotal_0 = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Subtotal 0%')
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor del descuento')
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Iva')
    total_iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor de iva')
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Total a pagar')
    sale = models.OneToOneField('Sale', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Venta generada')

    def __str__(self):
        return f'{self.formatted_number} = {self.client.get_full_name()}'

    @property
    def subtotal_without_taxes(self):
        return float(self.quotationdetail_set.filter().aggregate(result=Coalesce(Sum('subtotal'), 0.00, output_field=FloatField()))['result'])

    @property
    def formatted_number(self):
        return self.voucher_number_full if self.voucher_number_full else f'{self.id:08d}'

    def get_voucher_number_full(self):
        return f'{self.receipt.establishment_code}-{self.receipt.issuing_point_code}-{self.voucher_number}'

    def generate_voucher_number(self, increase=True):
        if isinstance(self.receipt.sequence, str):
            self.receipt.sequence = int(self.receipt.sequence)
        number = self.receipt.sequence + 1 if increase else self.receipt.sequence
        return f'{number:09d}'

    def generate_voucher_number_full(self):
        request = get_current_request()
        if self.company_id is None:
            self.company = request.tenant.company
        if self.receipt_id is None:
            self.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[3][0], establishment_code=self.company.establishment_code, issuing_point_code=self.company.issuing_point_code)
        self.voucher_number = self.generate_voucher_number()
        self.voucher_number_full = self.get_voucher_number_full()
        return self.voucher_number_full

    @property
    def validate_stock(self):
        return not self.quotationdetail_set.filter(product__inventoried=True, product__stock__lt=F('cant')).exists()

    def get_full_subtotal(self):
        return float(self.subtotal_0) + float(self.subtotal_12)

    def send_quotation_by_email(self):
        company = Company.objects.first()
        message = MIMEMultipart('alternative')
        message['Subject'] = f'Proforma {self.formatted_number} - {self.client.get_full_name()}'
        message['From'] = settings.EMAIL_HOST
        message['To'] = self.client.user.email
        content = f'Estimado(a)\n\n{self.client.user.names.upper()}\n\n'
        content += f'La cotización solicitada ha sido enviada a su correo electrónico para su revisión.\n\n'
        part = MIMEText(content)
        message.attach(part)
        context = {'quotation': self}
        pdf_creator = PDFCreator(template_name='quotation/invoice_pdf.html')
        pdf_file = pdf_creator.create(context=context)
        part = MIMEApplication(pdf_file, _subtype='pdf')
        part.add_header('Content-Disposition', 'attachment', filename=f'{self.formatted_number}.pdf')
        message.attach(part)
        if settings.DISABLE_REAL_EMAILS:
            print(f'[DISABLE_REAL_EMAILS] Correo de proforma {self.formatted_number} no enviado (destinatario: {message["To"]})')
        else:
            server = smtplib.SMTP(company.email_host, company.email_port)
            server.starttls()
            server.login(company.email_host_user, company.email_host_password)
            server.sendmail(company.email_host_user, message['To'], message.as_string())
            server.quit()

    def calculate_detail(self):
        for detail in self.quotationdetail_set.filter():
            detail.price = float(detail.price)
            detail.iva = float(self.iva)
            detail.price_with_vat = detail.price + (detail.price * detail.iva)
            detail.subtotal = detail.price * detail.cant
            detail.total_dscto = detail.subtotal * float(detail.dscto)
            detail.total_iva = (detail.subtotal - detail.total_dscto) * detail.iva
            detail.total = detail.subtotal - detail.total_dscto
            detail.save()

    def calculate_invoice(self):
        self.subtotal_0 = float(self.quotationdetail_set.filter(product__with_tax=False).aggregate(result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        self.subtotal_12 = float(self.quotationdetail_set.filter(product__with_tax=True).aggregate(result=Coalesce(Sum('total'), 0.00, output_field=FloatField()))['result'])
        # El IVA se calcula una sola vez sobre el subtotal ya sumado, no sumando el
        # IVA de cada línea (que ya viene redondeado a 2 decimales por la base de
        # datos) — sumar valores ya redondeados puede desviar el total en centavos.
        self.total_iva = round(self.subtotal_12 * float(self.iva), 2)
        self.total_dscto = float(self.quotationdetail_set.filter().aggregate(result=Coalesce(Sum('total_dscto'), 0.00, output_field=FloatField()))['result'])
        self.total = float(self.get_full_subtotal()) + float(self.total_iva)
        self.save()

    def recalculate_invoice(self):
        self.calculate_detail()
        self.calculate_invoice()

    def create_invoice(self, observations='', payment_type='efectivo', payment_method='20', end_credit=None):
        data = dict()
        with transaction.atomic():
            details = [detail for detail in self.quotationdetail_set.all()]
            sale = Sale()
            sale.date_joined = datetime.now().date()
            sale.company = self.company
            sale.environment_type = sale.company.environment_type
            sale.receipt = Receipt.objects.get(voucher_type=VOUCHER_TYPE[0][0], establishment_code=sale.company.establishment_code, issuing_point_code=sale.company.issuing_point_code)
            sale.voucher_number = sale.generate_voucher_number()
            sale.voucher_number_full = sale.get_voucher_number_full()
            sale.employee_id = self.employee_id
            sale.client_id = self.client_id
            sale.iva = sale.company.tax_rate
            sale.observations = observations
            sale.create_electronic_invoice = True
            # Igual que en la venta directa (SaleCreateView): el plazo que
            # exige el SRI en la forma de pago se calcula solo -0 días salvo
            # a crédito, donde son los días reales hasta la fecha límite. Sin
            # esto, toda factura generada desde una cotización quedaba con el
            # default del modelo (31 días) sin importar el tipo de pago real.
            sale.payment_type = payment_type
            sale.payment_method = payment_method
            if payment_type == 'credito' and end_credit:
                end_date = datetime.strptime(end_credit, '%Y-%m-%d').date() if isinstance(end_credit, str) else end_credit
                sale.end_credit = end_date
                sale.time_limit = max((end_date - sale.date_joined).days, 0)
                sale.cash = 0.00
            else:
                sale.time_limit = 0
                sale.cash = float(sale.total)
            sale.save()
            for quotation_detail in details:
                product = quotation_detail.product
                if product.inventoried and product.stock < quotation_detail.cant:
                    raise ValueError(f'Stock insuficiente para {product.name} (disponible: {product.stock})')
                invoice_detail = SaleDetail.objects.create(
                    sale_id=sale.id,
                    product_id=product.id,
                    cant=quotation_detail.cant,
                    price=quotation_detail.price,
                    dscto=quotation_detail.dscto,
                )
                if invoice_detail.product.inventoried:
                    invoice_detail.product.register_movement(-invoice_detail.cant, 'venta', f'Venta {sale.voucher_number_full} (desde cotización)', user=_current_user())
            sale.recalculate_invoice()
            # La venta y el descuento de stock quedan aunque el SRI no
            # autorice de inmediato (no disponible, rechazo, etc.): se
            # vincula igual la cotización a la venta, que queda "Sin
            # Autorizar" y se puede reintentar después (botón manual o el
            # barrido automático nocturno), en vez de perder toda la
            # conversión como antes.
            invoice_data = sale.generate_electronic_invoice()
            if 'error' in invoice_data:
                SRI().create_voucher_errors(sale, invoice_data)
            self.sale = sale
            self.save(update_fields=['sale'])
            data = {
                'sale_id': sale.id,
                'ticket_url': f'/pos/sale/admin/print/invoice/{sale.id}/',
            }
            if invoice_data['resp']:
                data['pdf_url'] = invoice_data['print_url']
            else:
                error = invoice_data.get('error')
                data['sri_warning'] = error if isinstance(error, str) else 'El SRI no respondió o rechazó la autorización de la factura electrónica. La venta quedó registrada como "Sin Autorizar"; puede imprimir el ticket y más tarde generar la autorización manual o automáticamente.'
        return data

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.pk is None and self.receipt_id:
            self.receipt.sequence = int(self.voucher_number)
            self.receipt.save()
        super(Quotation, self).save()

    def toJSON(self):
        item = model_to_dict(self, exclude=['company'])
        item['number'] = self.formatted_number
        item['receipt'] = self.receipt.toJSON() if self.receipt_id else None
        item['client'] = self.client.toJSON()
        item['employee'] = self.employee.toJSON()
        item['sale'] = {'id': self.sale_id, 'voucher_number_full': self.sale.voucher_number_full} if self.sale_id else None
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['subtotal_0'] = float(self.subtotal_0)
        item['subtotal_12'] = float(self.subtotal_12)
        item['subtotal'] = self.get_full_subtotal()
        item['total_dscto'] = float(self.total_dscto)
        item['iva'] = float(self.iva)
        item['total_iva'] = float(self.total_iva)
        item['total'] = float(self.total)
        return item

    class Meta:
        verbose_name = 'Cotización'
        verbose_name_plural = 'Cotizaciones'
        default_permissions = ()
        permissions = (
            ('view_quotation', 'Can view Cotización'),
            ('add_quotation', 'Can add Cotización'),
            ('change_quotation', 'Can change Cotización'),
            ('delete_quotation', 'Can delete Cotización'),
            ('print_quotation', 'Can print Cotización'),
        )


class QuotationDetail(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    cant = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    price_with_vat = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_iva = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_dscto = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.quotation.__str__()

    def toJSON(self):
        item = model_to_dict(self, exclude=['sale'])
        item['product'] = self.product.toJSON()
        item['price'] = float(self.price)
        item['price_with_vat'] = float(self.price_with_vat)
        item['subtotal'] = float(self.subtotal)
        item['iva'] = float(self.subtotal)
        item['total_iva'] = float(self.subtotal)
        item['dscto'] = float(self.dscto) * 100
        item['total_dscto'] = float(self.total_dscto)
        item['total'] = float(self.total)
        return item

    class Meta:
        verbose_name = 'Proforma Detalle'
        verbose_name_plural = 'Proforma Detalles'
        default_permissions = ()


class CashRegister(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Usuario')
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha')
    opening_datetime = models.DateTimeField(default=timezone.now, verbose_name='Fecha y hora de apertura')
    opening_amount = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Valor de apertura')
    opening_notes = models.CharField(max_length=500, null=True, blank=True, verbose_name='Observaciones de apertura')
    closing_datetime = models.DateTimeField(null=True, blank=True, verbose_name='Fecha y hora de cierre')
    counted_amount = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, verbose_name='Efectivo contado')
    expected_cash_amount = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, verbose_name='Efectivo esperado')
    difference = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, verbose_name='Diferencia')
    # Snapshot del desglose (ventas, abonos, pagos, gastos) calculado en el momento
    # del cierre, para que el historial no cambie si después se registran o
    # eliminan movimientos de ese mismo día.
    breakdown = models.JSONField(default=dict, blank=True, verbose_name='Detalle del cuadre')
    closing_notes = models.CharField(max_length=500, null=True, blank=True, verbose_name='Observaciones de cierre')
    # Cuánto del efectivo contado el cajero decide dejar físicamente en caja
    # para la apertura del siguiente día (no tiene que ser igual al valor de
    # apertura de hoy). Es solo una sugerencia para la próxima apertura, que
    # se puede ajustar si el conteo real de ese día no coincide.
    next_opening_amount = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True, verbose_name='Valor dejado para la próxima apertura')
    status = models.CharField(choices=CASH_REGISTER_STATUS, max_length=10, default=CASH_REGISTER_STATUS[0][0], verbose_name='Estado')

    def __str__(self):
        return f'{self.user.username} / {self.date_joined} / {self.get_status_display()}'

    def formatted_date_joined(self):
        return self.date_joined.strftime('%Y-%m-%d')

    def calculate_breakdown(self):
        return CashRegister.compute_breakdown(self.date_joined, user=self.user, opening_amount=float(self.opening_amount))

    @staticmethod
    def compute_breakdown(date, user=None, opening_amount=0.00):
        # user=None calcula el consolidado del día (todos los cajeros); con un
        # usuario puntual calcula el cuadre de esa sola caja. Misma lógica en
        # ambos casos para que el desglose por cajero y el consolidado del
        # admin siempre cuadren entre sí.
        r = lambda qs: float(qs.aggregate(r=Coalesce(Sum('total' if qs.model is Sale else 'valor'), 0.00, output_field=FloatField()))['r'])

        sales = Sale.objects.filter(date_joined=date)
        abonos = PaymentsCtaCollect.objects.filter(date_joined=date)
        pagos = PaymentsDebtsPay.objects.filter(date_joined=date)
        if user is not None:
            sales = sales.filter(employee=user)
            abonos = abonos.filter(created_by=user)
            pagos = pagos.filter(created_by=user)

        ventas_efectivo = r(sales.filter(payment_type='efectivo'))
        ventas_credito = r(sales.filter(payment_type='credito'))
        ventas_transferencia = r(sales.filter(payment_type='transferencia'))
        ventas_tarjeta = r(sales.filter(payment_type='tarjeta_credito'))
        ventas_total = ventas_efectivo + ventas_credito + ventas_transferencia + ventas_tarjeta

        abonos_efectivo = r(abonos.filter(payment_type='cash'))
        abonos_transferencia = r(abonos.filter(payment_type__in=['transfer', 'deposit']))
        abonos_cheque = r(abonos.filter(payment_type='check'))
        abonos_total = abonos_efectivo + abonos_transferencia + abonos_cheque

        pagos_efectivo = r(pagos.filter(payment_type='cash'))
        pagos_transferencia = r(pagos.filter(payment_type__in=['transfer', 'deposit']))
        pagos_cheque = r(pagos.filter(payment_type='check'))
        pagos_total = pagos_efectivo + pagos_transferencia + pagos_cheque

        # Los gastos no registran quién los creó ni su forma de pago, así que
        # se reportan como total del día (no por cajero) y se asumen en
        # efectivo para el cálculo del esperado, que es el caso más común de
        # caja chica. En el consolidado esto no se duplica: es el mismo total
        # del día para todos.
        gastos = float(Expenses.objects.filter(date_joined=date).aggregate(
            r=Coalesce(Sum('valor'), 0.00, output_field=FloatField()))['r'])

        expected_cash = float(opening_amount) + ventas_efectivo + abonos_efectivo - pagos_efectivo - gastos

        return {
            'opening_amount': float(opening_amount),
            'ventas_efectivo': ventas_efectivo,
            'ventas_transferencia': ventas_transferencia,
            'ventas_tarjeta': ventas_tarjeta,
            'ventas_credito': ventas_credito,
            'ventas_total': ventas_total,
            'abonos_efectivo': abonos_efectivo,
            'abonos_transferencia': abonos_transferencia,
            'abonos_cheque': abonos_cheque,
            'abonos_total': abonos_total,
            'pagos_efectivo': pagos_efectivo,
            'pagos_transferencia': pagos_transferencia,
            'pagos_cheque': pagos_cheque,
            'pagos_total': pagos_total,
            'gastos': gastos,
            'expected_cash': expected_cash,
        }

    def close(self, counted_amount, closing_notes=None, next_opening_amount=None):
        breakdown = self.calculate_breakdown()
        self.breakdown = breakdown
        self.expected_cash_amount = round(breakdown['expected_cash'], 2)
        self.counted_amount = counted_amount
        self.difference = round(float(counted_amount) - float(self.expected_cash_amount), 2)
        self.closing_notes = closing_notes
        self.closing_datetime = timezone.now()
        self.status = 'closed'
        self.next_opening_amount = next_opening_amount
        self.save()

    def toJSON(self):
        item = model_to_dict(self, exclude=['user'])
        item['user'] = self.user.toJSON() if hasattr(self.user, 'toJSON') else {'id': self.user.id, 'username': self.user.username}
        item['date_joined'] = self.date_joined.strftime('%Y-%m-%d')
        item['opening_datetime'] = self.opening_datetime.strftime('%Y-%m-%d %H:%M')
        item['closing_datetime'] = self.closing_datetime.strftime('%Y-%m-%d %H:%M') if self.closing_datetime else None
        item['opening_amount'] = float(self.opening_amount)
        item['counted_amount'] = float(self.counted_amount) if self.counted_amount is not None else None
        item['expected_cash_amount'] = float(self.expected_cash_amount) if self.expected_cash_amount is not None else None
        item['difference'] = float(self.difference) if self.difference is not None else None
        item['next_opening_amount'] = float(self.next_opening_amount) if self.next_opening_amount is not None else None
        return item

    class Meta:
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'
        default_permissions = ()
        permissions = (
            ('view_cashregister', 'Can view Caja'),
        )

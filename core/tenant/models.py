import base64
import os
import random
import shutil
import string
import time
from datetime import date, time as time_of_day
from os.path import basename

from django.core.files import File
from django.db import models
from django.forms import model_to_dict
from django.utils import timezone
from django_tenants.models import TenantMixin, DomainMixin
from django_tenants.utils import schema_rename, schema_context

from config import settings
from core.pos.choices import VOUCHER_TYPE, VAT_PERCENTAGE
from core.security.crypto import encrypt_value, decrypt_value
from core.security.fields import CustomImageField, CustomFileField
from core.tenant.choices import OBLIGATED_ACCOUNTING, ENVIRONMENT_TYPE, RETENTION_AGENT, EMISSION_TYPE, REGIMEN_RIMPE

PLAN_EXPIRATION_WARNING_DAYS = 30

BACKUP_FREQUENCY = (
    ('daily', 'Diario'),
    ('weekly', 'Semanal'),
)

BACKUP_WEEKDAY = (
    (0, 'Lunes'),
    (1, 'Martes'),
    (2, 'Miércoles'),
    (3, 'Jueves'),
    (4, 'Viernes'),
    (5, 'Sábado'),
    (6, 'Domingo'),
)


class ScheduledBackupMixin(models.Model):
    """Programación de respaldo automático y conexión a Google Drive.
    Se reutiliza tanto en Company (respaldo por compañía) como en
    ElectronicInvoicingProvider (respaldo general del sistema)."""
    backup_schedule_enabled = models.BooleanField(default=False, verbose_name='Respaldo automático habilitado')
    backup_schedule_frequency = models.CharField(max_length=10, choices=BACKUP_FREQUENCY, default='weekly', verbose_name='Frecuencia del respaldo')
    backup_schedule_weekday = models.PositiveSmallIntegerField(choices=BACKUP_WEEKDAY, null=True, blank=True, verbose_name='Día de la semana (respaldo semanal)')
    backup_schedule_time = models.TimeField(default=time_of_day(2, 0), verbose_name='Hora del respaldo')
    backup_schedule_last_run = models.DateTimeField(null=True, blank=True, verbose_name='Última ejecución automática')
    google_drive_refresh_token = models.TextField(null=True, blank=True, verbose_name='Token de Google Drive')
    google_drive_account_email = models.CharField(max_length=100, null=True, blank=True, verbose_name='Cuenta de Google Drive conectada')
    google_drive_folder_id = models.CharField(max_length=100, null=True, blank=True, verbose_name='Carpeta de Google Drive')

    class Meta:
        abstract = True

    @property
    def google_drive_connected(self):
        return bool(self.google_drive_refresh_token)

    def get_google_drive_refresh_token(self):
        return decrypt_value(self.google_drive_refresh_token)

    def set_google_drive_refresh_token(self, token):
        self.google_drive_refresh_token = encrypt_value(token)

    def disconnect_google_drive(self):
        self.google_drive_refresh_token = None
        self.google_drive_account_email = None
        self.google_drive_folder_id = None

    def is_backup_due(self, now=None):
        if not self.backup_schedule_enabled:
            return False
        now = now or timezone.localtime()
        if self.backup_schedule_last_run and timezone.localtime(self.backup_schedule_last_run).date() >= now.date():
            return False
        if now.time() < self.backup_schedule_time:
            return False
        if self.backup_schedule_frequency == 'weekly' and self.backup_schedule_weekday is not None \
                and now.weekday() != self.backup_schedule_weekday:
            return False
        return True

    def mark_backup_run(self, when=None):
        self.backup_schedule_last_run = when or timezone.now()
        self.save()


class Plan(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')
    quantity = models.PositiveIntegerField(verbose_name='Cantidad')

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        return f'{self.name} - {self.quantity}'

    def toJSON(self):
        item = model_to_dict(self)
        item['full_name'] = self.get_full_name()
        return item

    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Planes'


class ElectronicInvoicingProvider(ScheduledBackupMixin):
    """Datos del proveedor del sistema de facturación electrónica (quien
    desarrolla/comercializa este software), exigidos por el SRI en la
    Resolución NAC-DGERCGC26-00000027 (Registro Oficial 335, 28/07/2026).
    Se agregan como información adicional en cada Factura y Nota de Crédito.
    Registro único (singleton): editable desde el panel de administración
    por si el sistema se vende/transfiere a otro proveedor."""
    system_name = models.CharField(max_length=100, verbose_name='Nombre del sistema')
    ruc = models.CharField(max_length=13, verbose_name='RUC del proveedor')
    website = models.CharField(max_length=250, verbose_name='Sitio web')
    image = CustomImageField(null=True, blank=True, folder='electronic_invoicing_provider', scheme=settings.DEFAULT_SCHEMA, verbose_name='Logo')

    def __str__(self):
        return self.system_name

    def get_image(self):
        if self.image:
            return f'{settings.MEDIA_URL}{self.image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def toJSON(self):
        item = model_to_dict(self, exclude=['google_drive_refresh_token'])
        item['image'] = self.get_image()
        item['backup_schedule_time'] = self.backup_schedule_time.strftime('%H:%M') if self.backup_schedule_time else None
        item['backup_schedule_last_run'] = timezone.localtime(self.backup_schedule_last_run).strftime('%Y-%m-%d %H:%M') if self.backup_schedule_last_run else None
        return item

    class Meta:
        verbose_name = 'Proveedor de Facturación Electrónica'
        verbose_name_plural = 'Proveedor de Facturación Electrónica'
        default_permissions = ()
        permissions = (
            ('view_electronicinvoicingprovider', 'Can view Proveedor de Facturación Electrónica'),
            ('change_electronicinvoicingprovider', 'Can change Proveedor de Facturación Electrónica'),
        )


class Scheme(TenantMixin):
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)
    auto_create_schema = True

    def is_public(self):
        return self.name.lower() == 'public'

    def toJSON(self):
        item = model_to_dict(self, exclude=['created_on'])
        item['created_on'] = self.created_on.strftime('%Y-%m-%d') if self.created_on else None
        return item


class Company(ScheduledBackupMixin):
    ruc = models.CharField(max_length=13, verbose_name='Número de RUC')
    business_name = models.CharField(max_length=50, verbose_name='Razón social')
    tradename = models.CharField(max_length=50, verbose_name='Nombre Comercial')
    main_address = models.CharField(max_length=200, verbose_name='Dirección del Establecimiento Matriz')
    establishment_address = models.CharField(max_length=200, verbose_name='Dirección del Establecimiento Emisor')
    establishment_code = models.CharField(max_length=3, verbose_name='Código del Establecimiento Emisor')
    issuing_point_code = models.CharField(max_length=3, verbose_name='Código del Punto de Emisión')
    special_taxpayer = models.CharField(max_length=13, verbose_name='Contribuyente Especial (Número de Resolución)')
    obligated_accounting = models.CharField(max_length=2, choices=OBLIGATED_ACCOUNTING, default=OBLIGATED_ACCOUNTING[1][0], verbose_name='Obligado a Llevar Contabilidad')
    image = CustomImageField(null=True, blank=True, folder='company', scheme=settings.DEFAULT_SCHEMA, verbose_name='Logotipo de la empresa')
    environment_type = models.PositiveIntegerField(choices=ENVIRONMENT_TYPE, default=1, verbose_name='Tipo de Ambiente')
    emission_type = models.PositiveIntegerField(choices=EMISSION_TYPE, default=1, verbose_name='Tipo de Emisión')
    retention_agent = models.CharField(max_length=2, choices=RETENTION_AGENT, default=RETENTION_AGENT[1][0], verbose_name='Agente de Retención')
    regimen_rimpe = models.CharField(max_length=50, choices=REGIMEN_RIMPE, default=REGIMEN_RIMPE[0][0], null=True, blank=True, verbose_name='Regimen Tributario')
    enable_ticket_sale = models.BooleanField(default=True, verbose_name='Habilitar Ticket de Venta')
    enable_purchase_settlement = models.BooleanField(default=True, verbose_name='Habilitar Liquidación de Compra')
    invoice_auto_authorization_enabled = models.BooleanField(default=True, verbose_name='Autorización automática de facturas pendientes habilitada')
    invoice_auto_authorization_time = models.TimeField(default=time_of_day(23, 50), verbose_name='Hora de autorización automática de facturas pendientes')
    invoice_auto_authorization_last_run = models.DateTimeField(null=True, blank=True, verbose_name='Última ejecución automática de autorización de facturas')
    mobile = models.CharField(max_length=10, verbose_name='Teléfono celular')
    phone = models.CharField(max_length=9, verbose_name='Teléfono convencional')
    email = models.CharField(max_length=50, verbose_name='Email')
    website = models.CharField(max_length=250, verbose_name='Dirección de página web')
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name='Descripción')
    iva = models.DecimalField(default=15.00, decimal_places=2, max_digits=9, verbose_name='IVA')
    vat_percentage = models.IntegerField(choices=VAT_PERCENTAGE, default=VAT_PERCENTAGE[3][0], verbose_name='Porcentaje del IVA')
    electronic_signature = CustomFileField(null=True, blank=True, folder='company', scheme=settings.DEFAULT_SCHEMA, verbose_name='Firma electrónica (Archivo P12)')
    electronic_signature_key = models.CharField(max_length=100, verbose_name='Clave de firma electrónica')
    email_host = models.CharField(max_length=30, default='smtp.gmail.com', verbose_name='Servidor de correo')
    email_port = models.IntegerField(default=587, verbose_name='Puerto del servidor de correo')
    email_host_user = models.CharField(max_length=100, verbose_name='Username del servidor de correo')
    email_host_password = models.CharField(max_length=30, verbose_name='Password del servidor de correo')
    schema_name = models.CharField(max_length=30, null=True, blank=True, verbose_name='Nombre del esquema')
    scheme = models.OneToOneField(Scheme, on_delete=models.CASCADE, verbose_name='Esquema')
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, verbose_name='Plan de facturación')
    plan_start_date = models.DateField(null=True, blank=True, verbose_name='Fecha de inicio del plan')
    plan_end_date = models.DateField(null=True, blank=True, verbose_name='Fecha de fin del plan')
    plan_expiration_notified = models.BooleanField(default=False, verbose_name='Notificación de vencimiento enviada')
    representative_name = models.CharField(max_length=100, blank=True, default='', verbose_name='Nombre del representante legal')
    representative_position = models.CharField(max_length=100, blank=True, default='Representante Legal', verbose_name='Cargo del representante')
    active = models.BooleanField(default=True, verbose_name='Estado')

    def __str__(self):
        return self.business_name

    @property
    def days_until_plan_expires(self):
        if not self.plan_end_date:
            return None
        return (self.plan_end_date - date.today()).days

    @property
    def plan_is_expiring_soon(self):
        days = self.days_until_plan_expires
        return days is not None and 0 <= days <= PLAN_EXPIRATION_WARNING_DAYS

    @property
    def plan_is_expired(self):
        days = self.days_until_plan_expires
        return days is not None and days < 0

    @property
    def is_popular_business(self):
        return self.regimen_rimpe == REGIMEN_RIMPE[2][0]

    @property
    def is_retention_agent(self):
        return self.retention_agent == RETENTION_AGENT[0][0]

    @property
    def tax_rate(self):
        return float(self.iva) / 100

    def get_image(self):
        if self.image:
            return f'{settings.MEDIA_URL}{self.image}'
        return f'{settings.STATIC_URL}img/default/empty.png'

    def get_full_path_image(self):
        if self.image:
            return self.image.path
        return f'{settings.BASE_DIR}{settings.STATIC_URL}img/default/empty.png'

    def image_base64(self):
        try:
            if self.image:
                with open(self.image.path, 'rb') as image_file:
                    base64_data = base64.b64encode(image_file.read()).decode('utf-8')
                    extension = os.path.splitext(self.image.name)[1]
                    content_type = f'image/{extension.lstrip(".")}'
                    return f"data:{content_type};base64,{base64_data}"
        except:
            pass
        return None

    def get_iva(self):
        return float(self.iva)

    def get_electronic_signature(self):
        if self.electronic_signature:
            return f'{settings.MEDIA_URL}{self.electronic_signature}'
        return None

    def is_invoice_auto_authorization_due(self, now=None):
        if not self.invoice_auto_authorization_enabled:
            return False
        now = now or timezone.localtime()
        if self.invoice_auto_authorization_last_run and timezone.localtime(self.invoice_auto_authorization_last_run).date() >= now.date():
            return False
        if now.time() < self.invoice_auto_authorization_time:
            return False
        return True

    def mark_invoice_auto_authorization_run(self, when=None):
        self.invoice_auto_authorization_last_run = when or timezone.now()
        self.save()

    def toJSON(self):
        # electronic_signature_key (clave del .p12 ante el SRI), email_host_password
        # y google_drive_refresh_token NUNCA deben viajar al navegador: cualquier
        # pantalla que liste ventas, compañías, etc. termina incrustando
        # estos datos si no se excluyen aquí.
        item = model_to_dict(self, exclude=['electronic_signature_key', 'email_host_password', 'google_drive_refresh_token'])
        item['image'] = self.get_image()
        item['electronic_signature'] = self.get_electronic_signature()
        item['iva'] = float(self.iva)
        item['scheme'] = self.scheme.toJSON()
        item['plan'] = self.plan.toJSON()
        item['plan_start_date'] = self.plan_start_date.strftime('%Y-%m-%d') if self.plan_start_date else None
        item['plan_end_date'] = self.plan_end_date.strftime('%Y-%m-%d') if self.plan_end_date else None
        item['days_until_plan_expires'] = self.days_until_plan_expires
        item['backup_schedule_time'] = self.backup_schedule_time.strftime('%H:%M') if self.backup_schedule_time else None
        item['backup_schedule_last_run'] = timezone.localtime(self.backup_schedule_last_run).strftime('%Y-%m-%d %H:%M') if self.backup_schedule_last_run else None
        item['invoice_auto_authorization_time'] = self.invoice_auto_authorization_time.strftime('%H:%M') if self.invoice_auto_authorization_time else None
        item['invoice_auto_authorization_last_run'] = timezone.localtime(self.invoice_auto_authorization_last_run).strftime('%Y-%m-%d %H:%M') if self.invoice_auto_authorization_last_run else None
        return item

    def create_schema(self):
        scheme = Scheme.objects.create(name=self.schema_name, schema_name=self.schema_name)
        Domain.objects.create(domain=f'{scheme.schema_name}.{settings.DOMAIN}', tenant=scheme, is_primary=True)
        return scheme

    def create_base_modules(self):
        from core.user.models import User
        from core.security.models import Dashboard, ModuleType, Module, Group, GroupModule, GroupSettings, UserAccess, DatabaseBackups, Permission
        from core.pos.models import Provider, Category, Product, Purchase, PurchaseDetail, Client, Receipt, Sale, Quotation, SaleDetail, CtasCollect, PaymentsDebtsPay, DebtsPay, PaymentsDebtsPay, TypeExpense, Expenses, Promotions, PromotionsDetail, VoucherErrors, CreditNote, CreditNoteDetail, InventoryMovement
        from core.rrhh.models import Area, Position, Headings, Employee, Assistance, AssistanceDetail, Salary, SalaryDetail
        with schema_context(self.scheme.schema_name):
            dashboard = Dashboard.objects.create(
                name=self.tradename.upper(),
                author=self.business_name,
                icon='fas fa-shopping-cart',
                layout=1,
                navbar='navbar-dark navbar-navy',
                sidebar='sidebar-dark-navy'
            )
            image_path = f'{settings.BASE_DIR}{settings.STATIC_URL}img/default/logo.png'
            dashboard.image.save(basename(image_path), content=File(open(image_path, 'rb')), save=False)
            dashboard.save()

            modules_data = self.get_base_modules_data()

            for module_data in modules_data:
                module = Module.objects.create(
                    module_type=module_data['moduletype'],
                    name=module_data['name'],
                    url=module_data['url'],
                    icon=module_data['icon'],
                    description=module_data['description']
                )
                if module_data['permissions']:
                    for permission in module_data['permissions']:
                        module.permissions.add(permission)
                print(f'insertado {module.name}')

            group = Group.objects.create(name='Administrador')
            print(f'insertado {group.name}')

            EMPLOYEE_URLS = ['/rrhh/employee/update/profile/', '/rrhh/assistance/employee/', '/rrhh/salary/employee/']
            for module in Module.objects.filter().exclude(url__in=['/pos/client/update/profile/', '/pos/sale/client/', '/pos/credit/note/client/'] + EMPLOYEE_URLS):
                GroupModule.objects.create(module=module, group=group)
                for permission in module.permissions.all():
                    group.permissions.add(permission)
            # No es un módulo navegable (se ve directo en el dashboard), así que
            # el permiso se asigna aparte y no dentro del bucle de módulos.
            group.permissions.add(Permission.objects.get(codename='view_cashregister'))

            group = Group.objects.create(name='Cliente')
            print(f'insertado {group.name}')

            for module in Module.objects.filter(url__in=['/pos/client/update/profile/', '/pos/sale/client/', '/pos/credit/note/client/', '/user/update/password/']):
                GroupModule.objects.create(module=module, group=group)
                for permission in module.permissions.all():
                    group.permissions.add(permission)

            user = User.objects.create(
                names=self.tradename,
                username=self.ruc,
                email=self.email,
                is_active=True,
                is_superuser=True,
                is_staff=True
            )
            user.set_password(user.username)
            user.save()
            user.groups.add(Group.objects.get(pk=1))
            print(f'Bienvenido {user.names}')

            numbers = list(string.digits)
            for item in VOUCHER_TYPE:
                sequence = 1 if item[0] in [VOUCHER_TYPE[2][0], VOUCHER_TYPE[3][0]] else int(''.join(random.choices(numbers, k=7)))
                Receipt.objects.create(voucher_type=item[0], establishment_code=self.establishment_code, issuing_point_code=self.issuing_point_code, sequence=sequence)

            group = Group.objects.create(name='Empleado')
            print(f'insertado {group.name}')

            for module in Module.objects.filter(url__in=EMPLOYEE_URLS + ['/user/update/password/']):
                GroupModule.objects.create(module=module, group=group)
                for permission in module.permissions.all():
                    group.permissions.add(permission)

            group = Group.objects.create(name='Punto de Venta')
            print(f'insertado {group.name}')

            POINT_OF_SALE_URLS = ['/pos/sale/admin/', '/pos/client/', '/pos/ctas/collect/', '/pos/debts/pay/', '/pos/quotation/']
            for module in Module.objects.filter(url__in=POINT_OF_SALE_URLS + ['/user/update/password/']):
                GroupModule.objects.create(module=module, group=group)
                for permission in module.permissions.all():
                    group.permissions.add(permission)
            GroupSettings.objects.create(group=group, requires_cash_register=True)

    def get_base_modules_data(self):
        from core.security.models import Dashboard, ModuleType, Module, Group, GroupModule, GroupSettings, UserAccess, DatabaseBackups, Permission
        from core.pos.models import Provider, Category, Product, Purchase, PurchaseDetail, Client, Receipt, Sale, Quotation, SaleDetail, CtasCollect, PaymentsDebtsPay, DebtsPay, PaymentsDebtsPay, TypeExpense, Expenses, Promotions, PromotionsDetail, VoucherErrors, CreditNote, CreditNoteDetail, InventoryMovement, Combo, ComboDetail, PriceType
        from core.rrhh.models import Area, Position, Headings, Employee, Assistance, AssistanceDetail, Salary, SalaryDetail
        from core.user.models import User
        with schema_context(self.scheme.schema_name):
            moduletype, _ = ModuleType.objects.get_or_create(name='Seguridad', defaults={'icon': 'fas fa-lock'})
            print(f'insertado {moduletype.name}')

            modules_data = [
                {
                    'name': 'Tipos de Módulos',
                    'url': '/security/module/type/',
                    'icon': 'fas fa-door-open',
                    'description': 'Permite administrar los tipos de módulos del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=ModuleType._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Módulos',
                    'url': '/security/module/',
                    'icon': 'fas fa-th-large',
                    'description': 'Permite administrar los módulos del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Module._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Grupos',
                    'url': '/security/group/',
                    'icon': 'fas fa-users',
                    'description': 'Permite administrar los grupos de usuarios del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Group._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Respaldos',
                    'url': '/security/database/backups/',
                    'icon': 'fas fa-database',
                    'description': 'Permite administrar los respaldos de base de datos',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=DatabaseBackups._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Conf. Dashboard',
                    'url': '/security/dashboard/update/',
                    'icon': 'fas fa-tools',
                    'description': 'Permite configurar los datos de la plantilla',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Dashboard._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Accesos',
                    'url': '/security/user/access/',
                    'icon': 'fas fa-user-secret',
                    'description': 'Permite administrar los accesos de los usuarios',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=UserAccess._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Usuarios',
                    'url': '/user/',
                    'icon': 'fas fa-user',
                    'description': 'Permite administrar a los administradores del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=User._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Cambiar password',
                    'url': '/user/update/password/',
                    'icon': 'fas fa-key',
                    'description': 'Permite cambiar tu password de tu cuenta',
                    'moduletype': None,
                    'permissions': None
                },
                {
                    'name': 'Editar perfil',
                    'url': '/user/update/profile/',
                    'icon': 'fas fa-user',
                    'description': 'Permite cambiar la información de tu cuenta',
                    'moduletype': None,
                    'permissions': None
                }
            ]

            moduletype, _ = ModuleType.objects.get_or_create(name='Bodega', defaults={'icon': 'fas fa-boxes'})
            print(f'insertado {moduletype.name}')

            modules_data.extend([
                {
                    'name': 'Proveedores',
                    'url': '/pos/provider/',
                    'icon': 'fas fa-truck',
                    'description': 'Permite administrar a los proveedores de las compras',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Provider._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Categorías',
                    'url': '/pos/category/',
                    'icon': 'fas fa-truck-loading',
                    'description': 'Permite administrar las categorías de los productos',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Category._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Tipos de Precio',
                    'url': '/pos/price/type/update/',
                    'icon': 'fas fa-tags',
                    'description': 'Permite renombrar los tipos de precio (Distribuidor/Público/Tarjeta) usados en Productos, Combos y Clientes',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=PriceType._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Productos',
                    'url': '/pos/product/',
                    'icon': 'fas fa-box',
                    'description': 'Permite administrar los productos del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Product._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Combos',
                    'url': '/pos/combo/',
                    'icon': 'fas fa-boxes-stacked',
                    'description': 'Permite administrar los combos de productos que se venden como un solo ítem',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Combo._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Compras',
                    'url': '/pos/purchase/',
                    'icon': 'fas fa-dolly-flatbed',
                    'description': 'Permite administrar las compras de los productos',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Purchase._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Ajuste de Stock',
                    'url': '/pos/product/stock/adjustment/',
                    'icon': 'fas fa-sliders-h',
                    'description': 'Permite administrar los ajustes de stock de productos',
                    'moduletype': moduletype,
                    'permissions': [Permission.objects.get(codename='adjust_product_stock')]
                },
                {
                    'name': 'Kardex',
                    'url': '/pos/inventory/movement/',
                    'icon': 'fas fa-history',
                    'description': 'Permite consultar el historial de movimientos de inventario de los productos',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=InventoryMovement._meta.label.split('.')[1].lower()))
                }
            ])

            moduletype, _ = ModuleType.objects.get_or_create(name='Administrativo', defaults={'icon': 'fas fa-hand-holding-usd'})
            print(f'insertado {moduletype.name}')

            modules_data.extend([
                {
                    'name': 'Tipos de Gastos',
                    'url': '/pos/type/expense/',
                    'icon': 'fas fa-comments-dollar',
                    'description': 'Permite administrar los tipos de gastos',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=TypeExpense._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Gastos',
                    'url': '/pos/expenses/',
                    'icon': 'fas fa-file-invoice-dollar',
                    'description': 'Permite administrar los gastos de la compañia',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Expenses._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Cuentas por cobrar',
                    'url': '/pos/ctas/collect/',
                    'icon': 'fas fa-funnel-dollar',
                    'description': 'Permite administrar las cuentas por cobrar de los clientes',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=CtasCollect._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Cuentas por pagar',
                    'url': '/pos/debts/pay/',
                    'icon': 'fas fa-money-check-alt',
                    'description': 'Permite administrar las cuentas por pagar de los proveedores',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=DebtsPay._meta.label.split('.')[1].lower()))
                }
            ])

            moduletype, _ = ModuleType.objects.get_or_create(name='Facturación', defaults={'icon': 'fas fa-calculator'})
            print(f'insertado {moduletype.name}')

            modules_data.extend([
                {
                    'name': 'Comprobantes',
                    'url': '/pos/receipt/',
                    'icon': 'fas fa-file-export',
                    'description': 'Permite administrar los tipos de comprobantes para la facturación',
                    'moduletype': moduletype,
                    'order': 6,
                    'permissions': list(Permission.objects.filter(content_type__model=Receipt._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Clientes',
                    'url': '/pos/client/',
                    'icon': 'fas fa-user-friends',
                    'description': 'Permite administrar los clientes del sistema',
                    'moduletype': moduletype,
                    'order': 1,
                    'permissions': list(Permission.objects.filter(content_type__model=Client._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Ventas',
                    'url': '/pos/sale/admin/',
                    'icon': 'fas fa-shopping-cart',
                    'description': 'Permite administrar las ventas de los productos',
                    'moduletype': moduletype,
                    'order': 3,
                    'permissions': list(Permission.objects.filter(content_type__model=Sale._meta.label.split('.')[1].lower()).exclude(codename='view_sale_client'))
                },
                {
                    'name': 'Cotizaciones',
                    'url': '/pos/quotation/',
                    'icon': 'fa-solid fa-file-lines',
                    'description': 'Permite administrar las cotizaciones de los productos',
                    'moduletype': moduletype,
                    'order': 2,
                    'permissions': list(Permission.objects.filter(content_type__model=Quotation._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Notas de Credito',
                    'url': '/pos/credit/note/admin/',
                    'icon': 'fa-solid fa-boxes-packing',
                    'description': 'Permite administrar las notas de créditos de las ventas',
                    'moduletype': moduletype,
                    'order': 4,
                    'permissions': list(Permission.objects.filter(content_type__model=CreditNote._meta.label.split('.')[1].lower()).exclude(codename='view_credit_note_client'))
                },
                {
                    'name': 'Ventas',
                    'url': '/pos/sale/client/',
                    'icon': 'fas fa-shopping-cart',
                    'description': 'Permite administrar las ventas de los productos',
                    'moduletype': None,
                    'permissions': [Permission.objects.get(codename='view_sale_client')]
                },
                {
                    'name': 'Notas de Credito',
                    'url': '/pos/credit/note/client/',
                    'icon': 'fa-solid fa-boxes-packing',
                    'description': 'Permite administrar las notas de crédito de las ventas',
                    'moduletype': None,
                    'permissions': [Permission.objects.get(codename='view_credit_note_client')]
                },
                {
                    'name': 'Promociones',
                    'url': '/pos/promotions/',
                    'icon': 'far fa-calendar-check',
                    'description': 'Permite administrar las promociones de los productos',
                    'moduletype': moduletype,
                    'order': 5,
                    'permissions': list(Permission.objects.filter(content_type__model=Promotions._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Errores de Comprob.',
                    'url': '/pos/voucher/errors/',
                    'icon': 'fas fa-file-archive',
                    'description': 'Permite administrar los errores de los comprobantes de las facturas',
                    'moduletype': moduletype,
                    'order': 7,
                    'permissions': list(Permission.objects.filter(content_type__model=VoucherErrors._meta.label.split('.')[1].lower()))
                }
            ])

            moduletype, _ = ModuleType.objects.get_or_create(name='Recursos Humanos', defaults={'icon': 'fas fa-users'})
            print(f'insertado {moduletype.name}')

            modules_data.extend([
                {
                    'name': 'Areas',
                    'url': '/rrhh/area/',
                    'icon': 'fas fa-layer-group',
                    'description': 'Permite administrar las áreas del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Area._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Cargos',
                    'url': '/rrhh/position/',
                    'icon': 'fas fa-id-badge',
                    'description': 'Permite administrar los cargos del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Position._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Rubros',
                    'url': '/rrhh/headings/',
                    'icon': 'fas fa-percent',
                    'description': 'Permite administrar los rubros del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Headings._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Asistencias',
                    'url': '/rrhh/assistance/',
                    'icon': 'fa-solid fa-calendar-check',
                    'description': 'Permite administrar las asistencias de los empleados',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.exclude(codename='view_employee_assistance').filter(content_type__model=Assistance._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Empleados',
                    'url': '/rrhh/employee/',
                    'icon': 'fas fa-user-clock',
                    'description': 'Permite administrar los rubros del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.filter(content_type__model=Employee._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Salarios',
                    'url': '/rrhh/salary/',
                    'icon': 'fas fa-hand-holding-usd',
                    'description': 'Permite administrar los salarios del sistema',
                    'moduletype': moduletype,
                    'permissions': list(Permission.objects.exclude(codename='view_employee_salary').filter(content_type__model=Salary._meta.label.split('.')[1].lower()))
                },
                {
                    'name': 'Editar perfil',
                    'url': '/rrhh/employee/update/profile/',
                    'icon': 'fas fa-user',
                    'description': 'Permite cambiar la información de tu cuenta',
                    'moduletype': None,
                    'permissions': None
                },
                {
                    'name': 'Salarios',
                    'url': '/rrhh/salary/employee/',
                    'icon': 'fas fa-file-invoice-dollar',
                    'description': 'Permite ver a los empleados sus salarios',
                    'moduletype': None,
                    'permissions': [Permission.objects.get(codename='view_employee_salary')],
                },
                {
                    'name': 'Asistencias',
                    'url': '/rrhh/assistance/employee/',
                    'icon': 'fas fa-calendar-check',
                    'description': 'Permite ver a los empleados sus asistencias',
                    'moduletype': None,
                    'permissions': [Permission.objects.get(codename='view_employee_assistance')]
                }
            ])

            moduletype, _ = ModuleType.objects.get_or_create(name='Reportes', defaults={'icon': 'fas fa-chart-pie'})
            print(f'insertado {moduletype.name}')

            modules_data.extend([
                {
                    'name': 'Ventas',
                    'url': '/reports/sale/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de las ventas',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Ventas por Punto de Venta',
                    'url': '/reports/sale/point-of-sale/',
                    'icon': 'fas fa-cash-register',
                    'description': 'Permite ver las ventas diarias de cada punto de venta, en general o filtrado por fechas y por punto de venta puntual',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Productos con Stock Bajo',
                    'url': '/reports/product/low-stock/',
                    'icon': 'fas fa-exclamation-triangle',
                    'description': 'Permite ver los productos inventariados cuyo stock llegó al mínimo configurado o está en negativo',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Productos Más Vendidos',
                    'url': '/reports/product/best-sellers/',
                    'icon': 'fas fa-trophy',
                    'description': 'Permite ver los productos más vendidos en un rango de fechas',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Ventas por Producto',
                    'url': '/reports/product/sales/',
                    'icon': 'fas fa-search-dollar',
                    'description': 'Permite saber a quién se le vendió un producto (cliente, comprobante, fecha), o buscar por número de comprobante',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Compras',
                    'url': '/reports/purchase/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de las compras',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Gastos',
                    'url': '/reports/expenses/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de los gastos',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Cuentas por Pagar',
                    'url': '/reports/debts/pay/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de las cuentas por pagar',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Cuentas por Cobrar',
                    'url': '/reports/ctas/collect/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de las cuentas por cobrar',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Resultados',
                    'url': '/reports/results/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de pérdidas y ganancias',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Ganancias',
                    'url': '/reports/earnings/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver los reportes de las ganancias',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Ganancia Diaria',
                    'url': '/reports/earnings/daily/',
                    'icon': 'fas fa-coins',
                    'description': 'Permite ver la utilidad real por día (precio facturado según cliente vs. costo del producto)',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Horas Trabajadas',
                    'url': '/reports/hours/',
                    'icon': 'fas fa-chart-bar',
                    'description': 'Permite ver el reporte de horas trabajadas, horas extras y valor de pago de los empleados',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Marcaciones por Empleado',
                    'url': '/reports/hours/detail/',
                    'icon': 'fas fa-user-clock',
                    'description': 'Permite ver el detalle diario de marcaciones de un empleado, con atrasos y salidas anticipadas',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Comprobantes Anulados',
                    'url': '/reports/sale/canceled/',
                    'icon': 'fas fa-ban',
                    'description': 'Permite ver los comprobantes anulados por no haber sido autorizados por el SRI, con su clave de acceso, para gestionar su baja',
                    'moduletype': moduletype,
                    'permissions': None,
                },
                {
                    'name': 'Editar perfil',
                    'url': '/pos/client/update/profile/',
                    'icon': 'fas fa-user',
                    'description': 'Permite cambiar la información de tu cuenta',
                    'moduletype': None,
                    'permissions': None,
                },
                {
                    'name': 'Compañia',
                    'url': '/pos/company/update/',
                    'icon': 'fas fa-building',
                    'description': 'Permite gestionar la información de la compañia',
                    'moduletype': None,
                    'permissions': [Permission.objects.get(codename='change_company')]
                },
            ])

            return modules_data

    def rename_schema(self):
        self.scheme.name = self.schema_name
        self.scheme.save()
        domain = self.scheme.get_primary_domain()
        schema_rename(self.scheme, self.schema_name)
        time.sleep(1)
        if domain:
            domain.domain = f'{self.scheme.schema_name}.{settings.DOMAIN}'
            domain.save()

    def edit(self):
        super(Company, self).save()

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.pk is None or self.scheme is None:
            self.scheme = self.create_schema()
            self.create_base_modules()
        else:
            scheme = Scheme.objects.get(pk=self.scheme.pk)
            if scheme.schema_name != self.schema_name:
                self.rename_schema()
            previous = Company.objects.filter(pk=self.pk).values('plan_end_date').first()
            if previous and previous['plan_end_date'] != self.plan_end_date:
                self.plan_expiration_notified = False
        super(Company, self).save()

    def delete(self, using=None, keep_parents=False):
        path_dir = f'{settings.BASE_DIR}{settings.MEDIA_URL}{self.scheme.schema_name}'
        if os.path.exists(path_dir):
            shutil.rmtree(path_dir)
        with schema_context(self.scheme.schema_name):
            super(Company, self).delete()
        self.scheme.auto_drop_schema = True
        self.scheme.delete()

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'


class Domain(DomainMixin):
    pass

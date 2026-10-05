from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

ACCOUNT_TYPE = (
    ('activo', 'Activo'),
    ('pasivo', 'Pasivo'),
    ('patrimonio', 'Patrimonio'),
    ('ingreso', 'Ingreso'),
    ('costo', 'Costo'),
    ('gasto', 'Gasto'),
)

# Naturaleza del saldo: las cuentas de activo, costo y gasto aumentan por el
# Debe; las de pasivo, patrimonio e ingreso aumentan por el Haber.
DEBIT_NATURE_TYPES = ('activo', 'costo', 'gasto')

# Roles contables: qué cuenta del plan usa cada asiento automático. Se
# guardan en AccountMapping para que cada empresa pueda apuntarlos a su propia
# cuenta sin tocar código.
ROLES = (
    ('caja', 'Caja general'),
    ('banco_defecto', 'Banco por defecto'),
    ('tarjetas', 'Tarjetas de crédito por cobrar'),
    ('clientes', 'Clientes (cuentas por cobrar)'),
    ('proveedores', 'Proveedores (cuentas por pagar)'),
    ('inventario', 'Inventario de mercaderías'),
    ('iva_compras', 'Crédito tributario IVA en compras'),
    ('ret_iva', 'IVA retenido por clientes'),
    ('ret_renta', 'Impuesto a la renta retenido por clientes'),
    ('iva_ventas', 'IVA cobrado en ventas'),
    ('sueldos_pagar', 'Sueldos por pagar'),
    ('descuentos_nomina', 'Descuentos de nómina por pagar'),
    ('ventas_gravadas', 'Ventas con IVA'),
    ('ventas_0', 'Ventas tarifa 0%'),
    ('devoluciones', 'Devoluciones en ventas'),
    ('ingreso_defecto', 'Otros ingresos (por defecto)'),
    ('sobrante_caja', 'Sobrante de caja'),
    ('costo_ventas', 'Costo de ventas'),
    ('compras_no_inv', 'Compras no inventariables'),
    ('sueldos_gasto', 'Sueldos y salarios (gasto)'),
    ('gasto_defecto', 'Gastos generales (por defecto)'),
    ('gasto_bancario', 'Gastos bancarios'),
    ('faltante_caja', 'Faltante de caja'),
    ('redondeo', 'Ajuste por redondeo'),
)

SOURCE_TYPE = (
    ('sale', 'Venta'),
    ('credit_note', 'Nota de crédito'),
    ('collection', 'Cobro de cuenta por cobrar'),
    ('retention', 'Retención recibida'),
    ('purchase', 'Compra'),
    ('supplier_payment', 'Pago a proveedor'),
    ('expense', 'Gasto'),
    ('income', 'Ingreso'),
    ('cash_closing', 'Cierre de caja'),
    ('payroll', 'Nómina'),
    ('bank_move', 'Movimiento bancario'),
    ('manual', 'Asiento manual'),
)

ENTRY_STATUS = (
    ('posted', 'Registrado'),
    ('voided', 'Anulado'),
)

PERIOD_STATUS = (
    ('open', 'Abierto'),
    ('closed', 'Cerrado'),
)

BANK_ACCOUNT_TYPE = (
    ('ahorros', 'Ahorros'),
    ('corriente', 'Corriente'),
)


class AccountingConfig(models.Model):
    """Configuración única de la contabilidad de la empresa (un solo registro
    por schema)."""
    start_date = models.DateField(default=date.today, verbose_name='Fecha de inicio de la contabilidad')
    next_entry_number = models.PositiveIntegerField(default=1)
    activated_at = models.DateTimeField(default=timezone.now, verbose_name='Activada el')

    def __str__(self):
        return f'Contabilidad desde {self.start_date}'

    @classmethod
    def get(cls):
        return cls.objects.first()

    class Meta:
        verbose_name = 'Configuración contable'
        verbose_name_plural = 'Configuración contable'


class Account(models.Model):
    code = models.CharField(max_length=30, unique=True, verbose_name='Código')
    name = models.CharField(max_length=150, verbose_name='Nombre')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children', verbose_name='Cuenta padre')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE, verbose_name='Tipo')
    accepts_movement = models.BooleanField(default=True, verbose_name='Acepta movimientos')
    active = models.BooleanField(default=True, verbose_name='Activa')
    is_system = models.BooleanField(default=False, verbose_name='De sistema')

    def __str__(self):
        return f'{self.code} - {self.name}'

    @property
    def is_debit_nature(self):
        return self.account_type in DEBIT_NATURE_TYPES

    def toJSON(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'parent': self.parent_id,
            'parent_name': str(self.parent) if self.parent_id else '',
            'account_type': {'id': self.account_type, 'name': self.get_account_type_display()},
            'accepts_movement': self.accepts_movement,
            'active': self.active,
            'is_system': self.is_system,
            'text': str(self),
        }

    class Meta:
        verbose_name = 'Cuenta contable'
        verbose_name_plural = 'Plan de cuentas'
        ordering = ['code']


class AccountMapping(models.Model):
    role = models.CharField(max_length=30, unique=True, choices=ROLES, verbose_name='Rol')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='Cuenta')

    def __str__(self):
        return f'{self.get_role_display()} -> {self.account}'

    class Meta:
        verbose_name = 'Cuenta por rol'
        verbose_name_plural = 'Cuentas por rol'


class TypeAccountMapping(models.Model):
    """Cuenta contable de un Tipo de Gasto o de un Tipo de Ingreso del POS.
    Se guarda el id (no una FK) para no acoplar el esquema contable al de
    `pos`; si el tipo se borra, el mapeo huérfano es inofensivo."""
    kind = models.CharField(max_length=10, choices=(('expense', 'Gasto'), ('income', 'Ingreso')))
    type_id = models.PositiveIntegerField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='Cuenta')

    class Meta:
        verbose_name = 'Cuenta por tipo'
        verbose_name_plural = 'Cuentas por tipo'
        unique_together = ('kind', 'type_id')


class BankAccount(models.Model):
    bank_name = models.CharField(max_length=100, verbose_name='Banco')
    number = models.CharField(max_length=30, verbose_name='Número de cuenta')
    account_type = models.CharField(max_length=20, choices=BANK_ACCOUNT_TYPE, default='ahorros', verbose_name='Tipo de cuenta')
    holder = models.CharField(max_length=150, blank=True, default='', verbose_name='Titular')
    account = models.OneToOneField(Account, on_delete=models.PROTECT, editable=False, related_name='bank_account', verbose_name='Cuenta contable')
    active = models.BooleanField(default=True, verbose_name='Activa')
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return f'{self.bank_name} {self.account_type} {self.number}'

    def toJSON(self):
        return {
            'id': self.id,
            'bank_name': self.bank_name,
            'number': self.number,
            'account_type': {'id': self.account_type, 'name': self.get_account_type_display()},
            'holder': self.holder,
            'account': str(self.account),
            'active': self.active,
            'text': str(self),
        }

    class Meta:
        verbose_name = 'Cuenta bancaria'
        verbose_name_plural = 'Cuentas bancarias'
        unique_together = ('bank_name', 'number')


class BankAlias(models.Model):
    """El POS guarda el banco como texto libre (Sale.transfer_bank,
    PaymentsCtaCollect.bank_entity...). Un alias asocia ese texto a una cuenta
    bancaria real para que el asiento use la cuenta correcta."""
    text = models.CharField(max_length=100, unique=True, verbose_name='Texto tal como se escribe en el POS')
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='aliases', verbose_name='Cuenta bancaria')

    def __str__(self):
        return f'{self.text} -> {self.bank_account}'

    def toJSON(self):
        return {'id': self.id, 'text': self.text, 'bank_account': str(self.bank_account), 'bank_account_id': self.bank_account_id}

    class Meta:
        verbose_name = 'Alias de banco'
        verbose_name_plural = 'Alias de bancos'


class AccountingPeriod(models.Model):
    year = models.PositiveIntegerField(verbose_name='Año')
    month = models.PositiveIntegerField(verbose_name='Mes')
    status = models.CharField(max_length=10, choices=PERIOD_STATUS, default='open', verbose_name='Estado')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Cerrado el')
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='Cerrado por')

    def __str__(self):
        return f'{self.year}-{self.month:02d}'

    @classmethod
    def is_closed(cls, on_date):
        return cls.objects.filter(year=on_date.year, month=on_date.month, status='closed').exists()

    def toJSON(self):
        return {
            'id': self.id,
            'year': self.year,
            'month': self.month,
            'name': str(self),
            'status': {'id': self.status, 'name': self.get_status_display()},
            'closed_at': timezone.localtime(self.closed_at).strftime('%Y-%m-%d %H:%M') if self.closed_at else '',
            'closed_by': self.closed_by.names if self.closed_by_id else '',
        }

    class Meta:
        verbose_name = 'Período contable'
        verbose_name_plural = 'Períodos contables'
        unique_together = ('year', 'month')
        ordering = ['-year', '-month']


class JournalEntry(models.Model):
    number = models.PositiveIntegerField(unique=True, verbose_name='Número')
    date = models.DateField(db_index=True, verbose_name='Fecha contable')
    # Fecha y hora reales en que se registró el asiento (regla del proyecto:
    # toda actividad guarda fecha Y hora, no solo el día contable).
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Registrado el')
    updated_at = models.DateTimeField(default=timezone.now, verbose_name='Actualizado el')
    description = models.CharField(max_length=300, verbose_name='Descripción')
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE, db_index=True, verbose_name='Origen')
    source_id = models.PositiveIntegerField(null=True, blank=True)
    source_key = models.CharField(max_length=40, null=True, blank=True, unique=True)
    status = models.CharField(max_length=10, choices=ENTRY_STATUS, default='posted', db_index=True, verbose_name='Estado')
    void_reason = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name='Registrado por')
    total_debit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f'AS-{self.number:06d}'

    def recalculate_totals(self):
        lines = self.lines.all()
        self.total_debit = sum((i.debit for i in lines), Decimal('0.00'))
        self.total_credit = sum((i.credit for i in lines), Decimal('0.00'))
        self.save(update_fields=['total_debit', 'total_credit'])

    def toJSON(self):
        return {
            'id': self.id,
            'number': str(self),
            'date': self.date.strftime('%Y-%m-%d'),
            'created_at': timezone.localtime(self.created_at).strftime('%Y-%m-%d %H:%M'),
            'description': self.description,
            'source_type': {'id': self.source_type, 'name': self.get_source_type_display()},
            'source_id': self.source_id,
            'status': {'id': self.status, 'name': self.get_status_display()},
            'void_reason': self.void_reason,
            'total_debit': float(self.total_debit),
            'total_credit': float(self.total_credit),
        }

    @staticmethod
    def next_number():
        """Siguiente número de asiento. Debe llamarse dentro de una
        transacción: bloquea la fila de configuración para que dos asientos
        simultáneos no reciban el mismo número."""
        config = AccountingConfig.objects.select_for_update().first()
        number = config.next_entry_number
        config.next_entry_number = number + 1
        config.save(update_fields=['next_entry_number'])
        return number

    class Meta:
        verbose_name = 'Asiento contable'
        verbose_name_plural = 'Asientos contables'
        ordering = ['-date', '-number']


class JournalEntryLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='lines', verbose_name='Cuenta')
    debit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Debe')
    credit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Haber')
    description = models.CharField(max_length=300, blank=True, default='', verbose_name='Detalle')
    bank_account = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='lines', verbose_name='Cuenta bancaria')
    third_party = models.CharField(max_length=200, blank=True, default='', verbose_name='Tercero')
    third_party_id = models.CharField(max_length=20, blank=True, default='', verbose_name='Identificación')

    def toJSON(self):
        return {
            'id': self.id,
            'account': str(self.account),
            'account_id': self.account_id,
            'debit': float(self.debit),
            'credit': float(self.credit),
            'description': self.description,
            'third_party': self.third_party,
        }

    class Meta:
        verbose_name = 'Línea de asiento'
        verbose_name_plural = 'Líneas de asiento'
        constraints = [
            models.CheckConstraint(
                check=Q(debit__gte=0, credit__gte=0) & (Q(debit=0) | Q(credit=0)),
                name='contabilidad_line_debit_xor_credit',
            ),
        ]

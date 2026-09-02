from datetime import datetime, timedelta, time as time_type

from django.db import models
from django.forms import model_to_dict

from core.rrhh.choices import *
from core.user.models import User


class Area(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')

    def __str__(self):
        return self.name

    def toJSON(self):
        item = model_to_dict(self)
        return item

    class Meta:
        verbose_name = 'Area'
        verbose_name_plural = 'Areas'


class Position(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name='Nombre')

    def __str__(self):
        return self.name

    def toJSON(self):
        item = model_to_dict(self)
        return item

    class Meta:
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'


class Employee(models.Model):
    code = models.CharField(max_length=5, unique=True, verbose_name='Código de empleado')
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    dni = models.CharField(max_length=13, unique=True, verbose_name='Número de documento')
    hiring_date = models.DateField(default=datetime.now, verbose_name='Fecha de ingreso')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, verbose_name='Cargo')
    area = models.ForeignKey(Area, on_delete=models.PROTECT, verbose_name='Area')
    remuneration = models.DecimalField(max_digits=9, decimal_places=2, default=0.00, verbose_name='Remuneración')
    break_hours = models.DecimalField(max_digits=4, decimal_places=2, default=2.00, verbose_name='Horas de descanso/almuerzo')
    scheduled_check_in = models.TimeField(default=time_type(8, 0), verbose_name='Hora de entrada programada')
    scheduled_check_out = models.TimeField(default=time_type(18, 0), verbose_name='Hora de salida programada')

    def __str__(self):
        return self.get_full_name()

    def get_or_create_position(self, name):
        return Position.objects.get_or_create(name=name)[0]

    def get_or_create_area(self, name):
        return Area.objects.get_or_create(name=name)[0]

    def get_full_name(self):
        return f'{self.user.names} / {self.dni}'

    def get_amount_of_assists(self, year, month):
        return self.assistancedetail_set.filter(assistance__date_joined__year=year, assistance__date_joined__month=month, state=True).count()

    def get_hourly_rate(self):
        if not self.remuneration:
            return 0.0
        return round(float(self.remuneration) / MONTHLY_WORK_HOURS, 4)

    def scheduled_check_in_format(self):
        return self.scheduled_check_in.strftime('%H:%M')

    def scheduled_check_out_format(self):
        return self.scheduled_check_out.strftime('%H:%M')

    def hiring_date_format(self):
        return self.hiring_date.strftime('%Y-%m-%d')

    def delete(self, using=None, keep_parents=False):
        super(Employee, self).delete()
        try:
            self.user.delete()
        except:
            pass

    def toJSON(self):
        item = model_to_dict(self)
        item['user'] = self.user.toJSON()
        item['hiring_date'] = self.hiring_date.strftime('%Y-%m-%d')
        item['position'] = self.position.toJSON()
        item['area'] = self.area.toJSON()
        item['remuneration'] = float(self.remuneration)
        item['break_hours'] = float(self.break_hours)
        item['scheduled_check_in'] = self.scheduled_check_in_format()
        item['scheduled_check_out'] = self.scheduled_check_out_format()
        return item

    class Meta:
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'


class Headings(models.Model):
    name = models.CharField(max_length=200, unique=True, verbose_name='Nombre')
    code = models.CharField(max_length=30, unique=True, verbose_name='Referencia')
    type = models.CharField(max_length=15, choices=TYPE_HEADINGS, default='haberes', verbose_name='Tipo')
    state = models.BooleanField(default=True, verbose_name='Estado')
    order = models.IntegerField(default=0, verbose_name='Posición')
    has_quantity = models.BooleanField(default=False, verbose_name='¿Posee cantidad?')

    def __str__(self):
        return self.name

    def toJSON(self):
        item = model_to_dict(self)
        item['type'] = {'id': self.type, 'name': self.get_type_display()}
        return item

    def get_number(self):
        return f'{self.id:04d}'

    def get_amount_detail_salary(self, employee, year, month):
        return self.salaryheadings_set.filter(salary_detail__employee_id=employee, salary_detail__salary__year=year, salary_detail__salary__month=month).first()

    def convert_name_to_code(self):
        excludes = [' ', '.', '%']
        code = self.name.lower()
        for i in excludes:
            code = code.replace(i, '_')
        if code[-1] == '_':
            code = code[0:-1]
        return code

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        self.code = self.convert_name_to_code()
        super(Headings, self).save()

    class Meta:
        verbose_name = 'Rubro'
        verbose_name_plural = 'Rubros'


class Salary(models.Model):
    payment_date = models.DateField(default=datetime.now, verbose_name='Fecha de pago')
    year = models.IntegerField(verbose_name='Año')
    month = models.IntegerField(choices=MONTHS, default=0, verbose_name='Mes')

    def __str__(self):
        return self.payment_date.strftime('%Y-%m-%d')

    def toJSON(self):
        item = model_to_dict(self)
        item['payment_date'] = self.payment_date.strftime('%Y-%m-%d')
        item['month'] = {'id': self.month, 'name': self.get_month_display()}
        return item

    class Meta:
        verbose_name = 'Salario'
        verbose_name_plural = 'Salarios'
        default_permissions = ()
        permissions = (
            ('view_salary', 'Can view Salario | Admin'),
            ('add_salary', 'Can add Salario | Admin'),
            ('change_salary', 'Can change Salario | Admin'),
            ('delete_salary', 'Can delete Salario | Admin'),
            ('view_employee_salary', 'Can view Salario | Empleado'),
        )


class SalaryDetail(models.Model):
    salary = models.ForeignKey(Salary, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, verbose_name='Empleado')
    income = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    expenses = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.employee.user.names

    def get_income(self):
        return self.salaryheadings_set.filter(headings__type='haberes', valor__gt=0).order_by('headings__order')

    def get_expenses(self):
        return self.salaryheadings_set.filter(headings__type='descuentos', valor__gt=0).order_by('headings__order')

    def get_income_format(self):
        return float(self.income)

    def get_expenses_format(self):
        return float(self.expenses)

    def get_total_amount_format(self):
        return float(self.total_amount)

    def toJSON(self):
        item = model_to_dict(self)
        item['salary'] = self.salary.toJSON()
        item['employee'] = self.employee.toJSON()
        item['income'] = self.get_income_format()
        item['expenses'] = self.get_expenses_format()
        item['total_amount'] = self.get_total_amount_format()
        return item

    class Meta:
        verbose_name = 'Salario Detalle'
        verbose_name_plural = 'Salario Detalles'
        default_permissions = ()


class SalaryHeadings(models.Model):
    salary_detail = models.ForeignKey(SalaryDetail, on_delete=models.CASCADE)
    headings = models.ForeignKey(Headings, on_delete=models.PROTECT)
    cant = models.IntegerField(default=0)
    valor = models.DecimalField(max_digits=9, decimal_places=2, default=0.00)

    def __str__(self):
        return self.salary_detail.employee.user.names

    def get_cant(self):
        if self.headings.has_quantity:
            return self.cant
        return ' '

    def get_valor_format(self):
        return float(self.valor)

    def toJSON(self):
        item = model_to_dict(self, exclude=['salary'])
        item['valor'] = self.get_valor_format()
        return item

    class Meta:
        verbose_name = 'Detalle de Salario'
        verbose_name_plural = 'Detalle de Salarios'
        default_permissions = ()


class Assistance(models.Model):
    date_joined = models.DateField(default=datetime.now, verbose_name='Fecha de asistencia')
    year = models.IntegerField()
    month = models.IntegerField(choices=MONTHS, default=0)
    day = models.IntegerField()

    def __str__(self):
        return self.get_month_display()

    def date_joined_format(self):
        return self.date_joined.strftime('%Y-%m-%d')

    def toJSON(self):
        item = model_to_dict(self, exclude=['history'])
        item['date_joined'] = self.date_joined_format()
        item['month'] = {'id': self.month, 'name': self.get_month_display()}
        return item

    class Meta:
        verbose_name = 'Asistencia'
        verbose_name_plural = 'Asistencias'
        default_permissions = ()
        permissions = (
            ('view_assistance', 'Can view Asistencia | Admin'),
            ('add_assistance', 'Can add Asistencia | Admin'),
            ('change_assistance', 'Can change Asistencia | Admin'),
            ('delete_assistance', 'Can delete Asistencia | Admin'),
            ('view_employee_assistance', 'Can view Asistencia | Empleado'),
        )


STANDARD_WORKDAY_HOURS = 8
OVERTIME_SURCHARGE = 1.5
MONTHLY_WORK_HOURS = 240  # 30 días x 8 horas, referencia usada para calcular el valor de la hora


class AssistanceDetail(models.Model):
    assistance = models.ForeignKey(Assistance, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, verbose_name='Empleado')
    description = models.CharField(max_length=500, null=True, blank=True)
    state = models.BooleanField(default=False)
    check_in = models.TimeField(null=True, blank=True, verbose_name='Hora de entrada')
    check_out = models.TimeField(null=True, blank=True, verbose_name='Hora de salida')

    def __str__(self):
        return self.employee.get_full_name()

    def get_hours_worked(self):
        if not self.state or not self.check_in or not self.check_out:
            return 0.0
        entry = datetime.combine(self.assistance.date_joined, self.check_in)
        exit_ = datetime.combine(self.assistance.date_joined, self.check_out)
        if exit_ <= entry:
            exit_ += timedelta(days=1)
        total_hours = (exit_ - entry).total_seconds() / 3600
        worked_hours = total_hours - float(self.employee.break_hours or 0)
        return round(max(worked_hours, 0), 2)

    def get_regular_hours(self):
        return round(min(self.get_hours_worked(), STANDARD_WORKDAY_HOURS), 2)

    def get_overtime_hours(self):
        return round(max(self.get_hours_worked() - STANDARD_WORKDAY_HOURS, 0), 2)

    def check_in_format(self):
        return self.check_in.strftime('%H:%M') if self.check_in else None

    def check_out_format(self):
        return self.check_out.strftime('%H:%M') if self.check_out else None

    def get_late_minutes(self):
        if not self.state or not self.check_in:
            return 0
        scheduled = datetime.combine(self.assistance.date_joined, self.employee.scheduled_check_in)
        actual = datetime.combine(self.assistance.date_joined, self.check_in)
        return max(round((actual - scheduled).total_seconds() / 60), 0)

    def get_early_departure_minutes(self):
        if not self.state or not self.check_out:
            return 0
        scheduled = datetime.combine(self.assistance.date_joined, self.employee.scheduled_check_out)
        actual = datetime.combine(self.assistance.date_joined, self.check_out)
        return max(round((scheduled - actual).total_seconds() / 60), 0)

    def toJSON(self):
        item = model_to_dict(self)
        item['assistance'] = self.assistance.toJSON()
        item['employee'] = self.employee.toJSON()
        item['check_in'] = self.check_in_format()
        item['check_out'] = self.check_out_format()
        item['hours_worked'] = self.get_hours_worked()
        item['overtime_hours'] = self.get_overtime_hours()
        item['late_minutes'] = self.get_late_minutes()
        item['early_departure_minutes'] = self.get_early_departure_minutes()
        return item

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.description is None:
            self.description = 's/n'
        elif len(self.description) == 0:
            self.description = 's/n'
        super(AssistanceDetail, self).save()

    class Meta:
        verbose_name = 'Detalle de Asistencia'
        verbose_name_plural = 'Detalles de Asistencia'
        default_permissions = ()

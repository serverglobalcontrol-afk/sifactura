from datetime import datetime

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
    remuneration = models.FloatField(default=0.00, verbose_name='Remuneración')

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
    income = models.FloatField(default=0.00)
    expenses = models.FloatField(default=0.00)
    total_amount = models.FloatField(default=0.00)

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
    valor = models.FloatField(default=0.00)

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


class AssistanceDetail(models.Model):
    assistance = models.ForeignKey(Assistance, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, verbose_name='Empleado')
    description = models.CharField(max_length=500, null=True, blank=True)
    state = models.BooleanField(default=False)

    def __str__(self):
        return self.employee.get_full_name()

    def toJSON(self):
        item = model_to_dict(self)
        item['assistance'] = self.assistance.toJSON()
        item['employee'] = self.employee.toJSON()
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

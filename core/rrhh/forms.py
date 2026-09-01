from django import forms

from .models import *


class AreaForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Area
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ingrese un nombre'}),
        }

    def save(self, commit=True):
        data = {}
        try:
            if self.is_valid():
                super().save()
            else:
                data['error'] = self.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class PositionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Position
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ingrese un nombre'}),
        }

    def save(self, commit=True):
        data = {}
        try:
            if self.is_valid():
                super().save()
            else:
                data['error'] = self.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class HeadingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Headings
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ingrese un nombre'}),
            'code': forms.TextInput(attrs={'placeholder': 'Ingrese un código de referencia'}),
            'order': forms.TextInput(attrs={'placeholder': 'Ingrese una posición'}),
            'type': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
        }
        exclude = ['code']

    def save(self, commit=True):
        data = {}
        try:
            if self.is_valid():
                super().save()
            else:
                data['error'] = self.errors
        except Exception as e:
            data['error'] = str(e)
        return data


class EmployeeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Employee
        fields = '__all__'
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'Ingrese un código'}),
            'dni': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off', 'placeholder': 'Ingrese su número de documento'}),
            'position': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'area': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'hiring_date': forms.DateInput(attrs={
                'class': 'form-control datetimepicker-input',
                'id': 'hiring_date',
                'value': datetime.now().strftime('%Y-%m-%d'),
                'data-toggle': 'datetimepicker',
                'data-target': '#hiring_date'
            }),
            'remuneration': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'off',
                'placeholder': 'Ingrese una remuneración'
            }),
        }
        exclude = ['user']


class EmployeeUserForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in self.visible_fields():
            if type(i.field) in [forms.CharField, forms.ImageField, forms.FileField, forms.EmailField]:
                i.field.widget.attrs.update({
                    'class': 'form-control',
                    'autocomplete': 'off'
                })
        self.fields['names'].widget.attrs['autofocus'] = True

    class Meta:
        model = User
        fields = 'names', 'email', 'image'
        widgets = {
            'names': forms.TextInput(attrs={'placeholder': 'Ingrese sus nombres'}),
            'email': forms.TextInput(attrs={'placeholder': 'Ingrese su correo electrónico'}),
        }
        exclude = ['username', 'groups', 'is_active', 'is_change_password', 'is_staff', 'user_permissions', 'date_joined', 'last_login', 'is_superuser', 'email_reset_token']


class SalaryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Salary
        fields = '__all__'
        widgets = {
            'year': forms.TextInput(attrs={
                'class': 'form-control datetimepicker-input',
                'data-toggle': 'datetimepicker',
                'data-target': '#year',
                'value': datetime.now().year
            }),
            'month': forms.Select(attrs={
                'class': 'form-control select2',
                'style': 'width: 100%;'
            }),
        }

    year_month = forms.CharField(widget=forms.TextInput(
        attrs={
            'autocomplete': 'off',
            'placeholder': 'MM / AA',
            'class': 'form-control datetimepicker-input',
            'id': 'year_month',
            'data-toggle': 'datetimepicker',
            'data-target': '#year_month',
        }
    ), label='Año/Mes')

    employee = forms.ChoiceField(widget=forms.SelectMultiple(attrs={
        'class': 'form-control select2',
        'multiple': 'multiple',
        'style': 'width: 100%;'
    }), label='Empleado')


class AssistanceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Assistance
        fields = '__all__'
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'date_joined': forms.DateInput(format='%Y-%m-%d', attrs={
                'class': 'form-control datetimepicker-input',
                'id': 'date_joined',
                'value': datetime.now().strftime('%Y-%m-%d'),
                'data-toggle': 'datetimepicker',
                'data-target': '#date_joined'
            }),
        }

    date_range = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'autocomplete': 'off'
    }), label='Buscar por rango de fechas')

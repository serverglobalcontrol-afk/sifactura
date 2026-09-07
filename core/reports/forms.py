from django import forms

from core.pos.models import Product, Receipt
from core.rrhh.models import Employee
from core.user.models import User


class ReportForm(forms.Form):
    date_range = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'autocomplete': 'off'
    }), label='Buscar por rango de fechas')

    sale = forms.ChoiceField(widget=forms.Select(attrs={
        'class': 'form-control select2',
        'style': 'width: 100%;'
    }), label='Venta')

    product = forms.ModelChoiceField(widget=forms.SelectMultiple(attrs={
        'class': 'form-control select2',
    }), queryset=Product.objects.all(), label='Producto')

    receipt = forms.ModelChoiceField(widget=forms.Select(attrs={
        'class': 'form-control select2',
        'style': 'width: 100%;'
    }), queryset=Receipt.objects.all().order_by('id'), label='Comprobante')


class SalePointOfSaleReportForm(forms.Form):
    date_range = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'autocomplete': 'off'
    }), label='Buscar por rango de fechas')

    employee = forms.ModelChoiceField(widget=forms.Select(attrs={
        'class': 'form-control select2',
        'style': 'width: 100%;'
    }), queryset=User.objects.none(), required=False, empty_label='Todos', label='Punto de Venta')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo se listan como filtro los usuarios que realmente han
        # registrado ventas (no todo el catálogo de usuarios).
        self.fields['employee'].queryset = User.objects.filter(sale__isnull=False).distinct().order_by('names')


class HoursReportForm(forms.Form):
    date_range = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'autocomplete': 'off'
    }), label='Buscar por rango de fechas')

    employee = forms.ModelChoiceField(widget=forms.SelectMultiple(attrs={
        'class': 'form-control select2',
        'style': 'width: 100%;'
    }), queryset=Employee.objects.all(), required=False, label='Empleado')


class HoursDetailReportForm(forms.Form):
    date_range = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'autocomplete': 'off'
    }), label='Buscar por rango de fechas')

    employee = forms.ModelChoiceField(widget=forms.Select(attrs={
        'class': 'form-control select2',
        'style': 'width: 100%;'
    }), queryset=Employee.objects.all(), label='Empleado')

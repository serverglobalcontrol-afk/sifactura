from django import forms

from core.pos.models import Product, Receipt
from core.rrhh.models import Employee


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

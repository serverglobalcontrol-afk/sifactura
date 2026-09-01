from django import forms

from core.tenant.models import Company, ElectronicInvoicingProvider, Plan


class ElectronicInvoicingProviderForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['system_name'].widget.attrs['autofocus'] = True
        for i in self.visible_fields():
            i.field.widget.attrs.update({'class': 'form-control', 'autocomplete': 'off'})

    class Meta:
        model = ElectronicInvoicingProvider
        fields = '__all__'
        widgets = {
            'system_name': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del sistema'}),
            'ruc': forms.TextInput(attrs={'placeholder': 'Ingrese el RUC del proveedor'}),
            'website': forms.TextInput(attrs={'placeholder': 'Ingrese el sitio web'}),
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


class PlanForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['autofocus'] = True

    class Meta:
        model = Plan
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Ingrese un nombre'}),
            'quantity': forms.TextInput()
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


class CompanyForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ruc'].widget.attrs['autofocus'] = True
        for i in self.visible_fields():
            if type(i.field) in [forms.CharField, forms.ImageField, forms.FileField, forms.IntegerField]:
                i.field.widget.attrs.update({
                    'class': 'form-control',
                    'autocomplete': 'off'
                })

    class Meta:
        model = Company
        fields = '__all__'
        widgets = {
            'ruc': forms.TextInput(attrs={'placeholder': 'Ingrese un ruc'}),
            'business_name': forms.TextInput(attrs={'placeholder': 'Ingrese un nombre de razón social'}),
            'tradename': forms.TextInput(attrs={'placeholder': 'Ingrese un nombre comercial'}),
            'main_address': forms.TextInput(attrs={'placeholder': 'Ingrese una dirección principal'}),
            'establishment_address': forms.TextInput(attrs={'placeholder': 'Ingrese una dirección establecimiento'}),
            'issuing_point_code': forms.TextInput(attrs={'placeholder': 'Ingrese un código de punto de emisión'}),
            'establishment_code': forms.TextInput(attrs={'placeholder': 'Ingrese un código de establecimiento'}),
            'special_taxpayer': forms.TextInput(attrs={'placeholder': 'Ingrese un número de resolución'}),
            'obligated_accounting': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'environment_type': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'emission_type': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'retention_agent': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'regimen_rimpe': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'mobile': forms.TextInput(attrs={'placeholder': 'Ingrese un teléfono celular'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Ingrese un teléfono convencional'}),
            'email': forms.TextInput(attrs={'placeholder': 'Ingrese un email'}),
            'website': forms.TextInput(attrs={'placeholder': 'Ingrese una dirección web'}),
            'description': forms.TextInput(attrs={'placeholder': 'Ingrese una descripción'}),
            'iva': forms.TextInput(attrs={
                'class': 'form-control',
                'autocomplete': 'off'
            }),
            'vat_percentage': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'electronic_signature_key': forms.TextInput(attrs={'placeholder': 'Ingrese la clave de la firma electrónica'}),
            'email_host': forms.TextInput(attrs={'placeholder': 'Ingrese el servidor de correo'}),
            'email_port': forms.TextInput(attrs={'placeholder': 'Ingrese el puerto de servidor de correo'}),
            'email_host_user': forms.TextInput(attrs={'placeholder': 'Ingrese el username del servidor de correo'}),
            'email_host_password': forms.TextInput(attrs={'placeholder': 'Ingrese el password del servidor de correo'}),
            'domain': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del dominio'}),
            'schema_name': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del esquema'}),
            'plan': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'plan_start_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'plan_end_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'representative_name': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del representante legal'}),
            'representative_position': forms.TextInput(attrs={'placeholder': 'Ingrese el cargo del representante'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-control-checkbox'})
        }
        exclude = ['scheme', 'plan_expiration_notified']

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

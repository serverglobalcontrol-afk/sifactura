from django import forms

from core.tenant.models import Company, ElectronicInvoicingProvider, Plan


def build_field_groups(form, groups):
    return [
        (icon, label, [form[name] for name in names if name in form.fields])
        for icon, label, names in groups
    ]


PROVIDER_FIELD_GROUPS = [
    ('fas fa-file-signature', 'Datos del proveedor', [
        'system_name', 'ruc', 'website', 'image',
    ]),
    ('fas fa-clock', 'Respaldo automático (respaldo general del sistema)', [
        'backup_schedule_enabled', 'backup_schedule_frequency', 'backup_schedule_weekday', 'backup_schedule_time',
    ]),
]


class ElectronicInvoicingProviderForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['system_name'].widget.attrs['autofocus'] = True
        for i in self.visible_fields():
            i.field.widget.attrs.update({'class': 'form-control', 'autocomplete': 'off'})

    class Meta:
        model = ElectronicInvoicingProvider
        fields = '__all__'
        exclude = ['backup_schedule_last_run', 'google_drive_refresh_token', 'google_drive_account_email', 'google_drive_folder_id']
        widgets = {
            'system_name': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del sistema'}),
            'ruc': forms.TextInput(attrs={'placeholder': 'Ingrese el RUC del proveedor'}),
            'website': forms.TextInput(attrs={'placeholder': 'Ingrese el sitio web'}),
            'backup_schedule_enabled': forms.CheckboxInput(attrs={'class': 'form-control-checkbox'}),
            'backup_schedule_frequency': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'backup_schedule_weekday': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'backup_schedule_time': forms.TimeInput(format='%H:%M', attrs={'class': 'form-control', 'type': 'time'}),
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


PROTECTED_FIELDS = ('electronic_signature_key', 'email_host_password')

COMPANY_FIELD_GROUPS = [
    ('fas fa-building', 'Datos generales', [
        'ruc', 'business_name', 'tradename', 'active',
    ]),
    ('fas fa-file-invoice', 'Datos para el SRI', [
        'main_address', 'establishment_address', 'establishment_code', 'issuing_point_code', 'special_taxpayer',
        'obligated_accounting', 'environment_type', 'emission_type', 'retention_agent', 'regimen_rimpe',
        'iva', 'vat_percentage',
    ]),
    ('fas fa-user-tie', 'Representante legal', [
        'representative_name', 'representative_position',
    ]),
    ('fas fa-address-book', 'Contacto', [
        'mobile', 'phone', 'email', 'website', 'description',
    ]),
    ('fas fa-file-signature', 'Logo y firma electrónica', [
        'image', 'electronic_signature', 'electronic_signature_key',
    ]),
    ('fas fa-envelope', 'Configuración de correo', [
        'email_host', 'email_port', 'email_host_user', 'email_host_password',
    ]),
    ('fas fa-toolbox', 'Plan y datos del sistema', [
        'schema_name', 'plan', 'plan_start_date', 'plan_end_date',
    ]),
    ('fas fa-clock', 'Respaldo automático', [
        'backup_schedule_enabled', 'backup_schedule_frequency', 'backup_schedule_weekday', 'backup_schedule_time',
    ]),
]



class CompanyForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se guarda el valor real antes de que el widget de password lo
        # oculte, para poder conservarlo si se guarda el formulario sin
        # volver a escribirlo (ver save()).
        self._original_protected_values = {
            field: getattr(self.instance, field, '') for field in PROTECTED_FIELDS
        } if self.instance.pk else {}
        for field in PROTECTED_FIELDS:
            # Al editar, dejarlo en blanco significa "no cambiar la clave
            # actual", así que no puede seguir siendo obligatorio. Al crear
            # una compañía nueva sigue siendo requerido, como antes.
            if self.instance.pk and field in self.fields:
                self.fields[field].required = False
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
            'electronic_signature_key': forms.PasswordInput(attrs={'placeholder': 'Ingrese la clave de la firma electrónica'}, render_value=False),
            'email_host': forms.TextInput(attrs={'placeholder': 'Ingrese el servidor de correo'}),
            'email_port': forms.TextInput(attrs={'placeholder': 'Ingrese el puerto de servidor de correo'}),
            'email_host_user': forms.TextInput(attrs={'placeholder': 'Ingrese el username del servidor de correo'}),
            'email_host_password': forms.PasswordInput(attrs={'placeholder': 'Dejar en blanco para no modificar'}, render_value=False),
            'domain': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del dominio'}),
            'schema_name': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del esquema'}),
            'plan': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'plan_start_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'plan_end_date': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'representative_name': forms.TextInput(attrs={'placeholder': 'Ingrese el nombre del representante legal'}),
            'representative_position': forms.TextInput(attrs={'placeholder': 'Ingrese el cargo del representante'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-control-checkbox'}),
            'backup_schedule_enabled': forms.CheckboxInput(attrs={'class': 'form-control-checkbox'}),
            'backup_schedule_frequency': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'backup_schedule_weekday': forms.Select(attrs={'class': 'form-control select2', 'style': 'width: 100%;'}),
            'backup_schedule_time': forms.TimeInput(format='%H:%M', attrs={'class': 'form-control', 'type': 'time'}),
        }
        exclude = [
            'scheme', 'plan_expiration_notified',
            'backup_schedule_last_run', 'google_drive_refresh_token', 'google_drive_account_email', 'google_drive_folder_id',
        ]

    def save(self, commit=True):
        data = {}
        try:
            if self.is_valid():
                # Los campos de tipo password se envían vacíos si el usuario no
                # los vuelve a escribir (no se re-muestra su valor actual por
                # seguridad); en ese caso se conserva el valor que ya existía
                # en vez de sobreescribirlo con un valor en blanco.
                for field, original_value in self._original_protected_values.items():
                    if not self.cleaned_data.get(field):
                        setattr(self.instance, field, original_value)
                super().save()
            else:
                data['error'] = self.errors
        except Exception as e:
            data['error'] = str(e)
        return data

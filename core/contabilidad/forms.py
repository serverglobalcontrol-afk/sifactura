from datetime import date

from django import forms

from core.contabilidad.models import (
    ACCOUNT_TYPE, Account, AccountMapping, AccountingConfig, BankAccount, BankAlias, ROLES, TypeAccountMapping,
)
from core.contabilidad.services.accounts import create_bank_account


class SaveAsDictMixin:
    """Mismo contrato que los formularios del POS: save() devuelve un dict
    ({} si todo salió bien, {'error': ...} si no) en vez de la instancia, para
    responder directo en JSON."""

    def save(self, commit=True):
        data = {}
        try:
            if self.is_valid():
                self.save_instance()
            else:
                data['error'] = self.errors
        except Exception as e:
            data['error'] = str(e)
        return data

    def save_instance(self):
        super().save()


class AccountForm(SaveAsDictMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = Account.objects.all().order_by('code')
        self.fields['parent'].required = False
        self.fields['code'].widget.attrs['autofocus'] = True
        if self.instance.pk and self.instance.is_system:
            # Las cuentas base se pueden renombrar, pero no cambiar de
            # naturaleza ni de código (los roles automáticos dependen de ellas).
            self.fields['code'].disabled = True
            self.fields['account_type'].disabled = True

    class Meta:
        model = Account
        fields = ['code', 'name', 'parent', 'account_type', 'accepts_movement', 'active']
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': 'Ej: 1.1.01.04'}),
            'name': forms.TextInput(attrs={'placeholder': 'Nombre de la cuenta'}),
        }


class BankAccountForm(SaveAsDictMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bank_name'].widget.attrs['autofocus'] = True

    class Meta:
        model = BankAccount
        fields = ['bank_name', 'number', 'account_type', 'holder', 'active']
        widgets = {
            'bank_name': forms.TextInput(attrs={'placeholder': 'Ej: Banco Pichincha'}),
            'number': forms.TextInput(attrs={'placeholder': 'Número de cuenta'}),
            'holder': forms.TextInput(attrs={'placeholder': 'Titular de la cuenta'}),
        }

    def save_instance(self):
        cd = self.cleaned_data
        if self.instance.pk:
            bank = super(SaveAsDictMixin, self).save()
            account = bank.account
            account.name = f'{bank.bank_name} {bank.account_type} {bank.number}'[:150]
            account.active = bank.active
            account.save(update_fields=['name', 'active'])
        else:
            create_bank_account(cd['bank_name'], cd['number'], cd['account_type'], cd.get('holder') or '')


class BankAliasForm(SaveAsDictMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['text'].widget.attrs['autofocus'] = True
        self.fields['bank_account'].queryset = BankAccount.objects.filter(active=True)

    class Meta:
        model = BankAlias
        fields = ['text', 'bank_account']
        widgets = {
            'text': forms.TextInput(attrs={'placeholder': 'Ej: pichincha, bco pichincha'}),
        }


class BankMoveForm(forms.Form):
    KINDS = (
        ('deposit', 'Depósito de caja a banco'),
        ('withdrawal', 'Retiro de banco a caja'),
        ('transfer', 'Transferencia entre cuentas bancarias'),
        ('fee', 'Comisión o gasto bancario'),
    )
    kind = forms.ChoiceField(choices=KINDS, label='Tipo de movimiento')
    date = forms.DateField(initial=date.today, label='Fecha', widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2, label='Valor')
    bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.none(), label='Cuenta bancaria (origen)')
    other_bank_account = forms.ModelChoiceField(queryset=BankAccount.objects.none(), required=False, label='Cuenta bancaria destino (solo transferencias)')
    description = forms.CharField(required=False, max_length=200, label='Detalle')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active = BankAccount.objects.filter(active=True)
        self.fields['bank_account'].queryset = active
        self.fields['other_bank_account'].queryset = active


class AccountingConfigForm(forms.Form):
    """Fecha de inicio + una lista desplegable por cada rol contable + una por
    cada tipo de gasto/ingreso del POS."""
    start_date = forms.DateField(label='Fecha de inicio de la contabilidad', widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        from core.pos.models import TypeExpense, TypeIncome
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(accepts_movement=True, active=True).order_by('code')
        config = AccountingConfig.get()
        self.fields['start_date'].initial = config.start_date if config else date.today()
        current = {m.role: m.account_id for m in AccountMapping.objects.all()}
        for role, label in ROLES:
            self.fields[f'role_{role}'] = forms.ModelChoiceField(queryset=accounts, label=label, initial=current.get(role))
        types = {(m.kind, m.type_id): m.account_id for m in TypeAccountMapping.objects.all()}
        for item in TypeExpense.objects.order_by('name'):
            self.fields[f'expense_{item.pk}'] = forms.ModelChoiceField(
                queryset=accounts, required=False, label=f'Gasto: {item.name}', initial=types.get(('expense', item.pk)),
                empty_label='(usar la cuenta de gastos por defecto)')
        for item in TypeIncome.objects.order_by('name'):
            self.fields[f'income_{item.pk}'] = forms.ModelChoiceField(
                queryset=accounts, required=False, label=f'Ingreso: {item.name}', initial=types.get(('income', item.pk)),
                empty_label='(usar la cuenta de otros ingresos por defecto)')

    def role_fields(self):
        return [self[f'role_{role}'] for role, _ in ROLES]

    def expense_fields(self):
        return [self[n] for n in self.fields if n.startswith('expense_')]

    def income_fields(self):
        return [self[n] for n in self.fields if n.startswith('income_')]

    def save(self):
        data = {}
        try:
            if not self.is_valid():
                return {'error': self.errors}
            cd = self.cleaned_data
            config = AccountingConfig.get()
            config.start_date = cd['start_date']
            config.save(update_fields=['start_date'])
            for role, _ in ROLES:
                AccountMapping.objects.update_or_create(role=role, defaults={'account': cd[f'role_{role}']})
            for name, account in cd.items():
                if name.startswith(('expense_', 'income_')):
                    kind, type_id = name.split('_', 1)
                    if account is None:
                        TypeAccountMapping.objects.filter(kind=kind, type_id=int(type_id)).delete()
                    else:
                        TypeAccountMapping.objects.update_or_create(kind=kind, type_id=int(type_id), defaults={'account': account})
        except Exception as e:
            data['error'] = str(e)
        return data

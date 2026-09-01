from django import forms

from core.marketing.models import MarketingPage, Promotion


class MarketingPageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hero_title'].widget.attrs['autofocus'] = True
        for i in self.visible_fields():
            if type(i.field) in [forms.CharField, forms.ImageField]:
                i.field.widget.attrs.update({'class': 'form-control', 'autocomplete': 'off'})

    class Meta:
        model = MarketingPage
        fields = '__all__'
        widgets = {
            'hero_title': forms.TextInput(attrs={'placeholder': 'Ingrese el título principal'}),
            'hero_subtitle': forms.TextInput(attrs={'placeholder': 'Ingrese el subtítulo'}),
            'footer_text': forms.TextInput(attrs={'placeholder': 'Ingrese el texto del footer'}),
            'facebook_url': forms.TextInput(attrs={'placeholder': 'https://facebook.com/...'}),
            'instagram_url': forms.TextInput(attrs={'placeholder': 'https://instagram.com/...'}),
            'twitter_url': forms.TextInput(attrs={'placeholder': 'https://x.com/...'}),
            'linkedin_url': forms.TextInput(attrs={'placeholder': 'https://linkedin.com/...'}),
            'whatsapp_number': forms.TextInput(attrs={'placeholder': 'Ingrese el número de WhatsApp'}),
            'contact_email': forms.TextInput(attrs={'placeholder': 'Ingrese el correo de contacto'}),
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


class PromotionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].widget.attrs['autofocus'] = True
        for i in self.visible_fields():
            if type(i.field) in [forms.CharField, forms.ImageField, forms.IntegerField]:
                i.field.widget.attrs.update({'class': 'form-control', 'autocomplete': 'off'})

    class Meta:
        model = Promotion
        fields = '__all__'
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Ingrese un título'}),
            'description': forms.TextInput(attrs={'placeholder': 'Ingrese una descripción'}),
            'link_text': forms.TextInput(attrs={'placeholder': 'Ej. Ver más'}),
            'link_url': forms.TextInput(attrs={'placeholder': 'Ingrese un enlace (opcional)'}),
            'order': forms.TextInput(attrs={'placeholder': 'Ingrese el orden'}),
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

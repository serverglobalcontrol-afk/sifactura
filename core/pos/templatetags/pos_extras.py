from django import forms
from django import template

register = template.Library()


@register.filter
def split_form_fields(form, quantity):
    list_of_fields = form.visible_fields()
    splitted_list = list()
    for i in range(0, len(list_of_fields), quantity):
        splitted_list.append(list_of_fields[i:i + quantity])
    return splitted_list


@register.filter
def chunk(a_list, quantity):
    quantity = int(quantity)
    return [a_list[i:i + quantity] for i in range(0, len(a_list), quantity)]


@register.filter
def field_col_class(field):
    """Ancho de columna Bootstrap acorde al dato del campo, para que un
    campo corto (hora, fecha, código de 3 dígitos) no ocupe el mismo
    espacio que un texto largo (dirección, descripción)."""
    widget = field.field.widget
    input_type = getattr(widget, 'input_type', None)

    override = widget.attrs.get('data-col-class')
    if override:
        return override

    if isinstance(widget, forms.Textarea):
        return 'col-12'
    if isinstance(widget, forms.CheckboxInput):
        return 'col-md-3 col-6'
    if input_type in ('time', 'date'):
        return 'col-md-2 col-6'
    if isinstance(widget, forms.Select):
        return 'col-md-3 col-6'
    if isinstance(widget, (forms.ClearableFileInput, forms.FileInput)):
        return 'col-md-4 col-12'

    max_length = getattr(field.field, 'max_length', None)
    if max_length:
        if max_length <= 15:
            return 'col-md-2 col-6'
        if max_length <= 60:
            return 'col-md-3 col-6'
        if max_length <= 120:
            return 'col-md-4 col-6'
        return 'col-md-6 col-12'

    return 'col-md-3 col-6'

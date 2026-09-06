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

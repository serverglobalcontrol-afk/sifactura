
from django.conf import settings
from django.template.loader import get_template
from weasyprint import CSS
from weasyprint import HTML

from config import settings


def create_pdf(context, template_name):
    template = get_template(template_name)
    html_template = template.render(context).encode(encoding="UTF-8")
    path_css = f'{settings.BASE_DIR}{settings.STATIC_URL}lib/bootstrap-4.6.0/css/bootstrap.min.css'
    # El stylesheet de impresión de Bootstrap fuerza `body{min-width:992px!important}`,
    # y WeasyPrint siempre renderiza en modo "print". Sin anular esto, el contenido
    # queda más ancho que una página A4 y se recorta. Va después en la lista para
    # que gane sobre la regla de Bootstrap.
    reset_css = CSS(string='body{min-width:0!important}.container{min-width:0!important}')
    pdf_file = HTML(string=html_template, base_url='.').write_pdf(stylesheets=[CSS(path_css), reset_css], presentational_hints=True)
    return pdf_file

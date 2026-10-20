
from crum import get_current_request
from django.template.loader import get_template
from weasyprint import HTML



class PDFCreator:
    def __init__(self, template_name):
        self.template_name = template_name

    def create(self, context):
        request = get_current_request()
        template = get_template(self.template_name)
        html_template = template.render(context).encode(encoding="UTF-8")
        if request:
            pdf_file = HTML(string=html_template, base_url=request.build_absolute_uri()).write_pdf(presentational_hints=True)
        else:
            pdf_file = HTML(string=html_template, base_url='.').write_pdf(presentational_hints=True)
        return pdf_file

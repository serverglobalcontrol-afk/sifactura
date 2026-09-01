from django.core.mail import send_mail
from django.core.management import BaseCommand

from config import settings
from core.tenant.models import Company


class Command(BaseCommand):
    help = "Send an email to companies whose billing plan is about to expire"

    def handle(self, *args, **options):
        companies = Company.objects.filter(
            active=True,
            plan_end_date__isnull=False,
            plan_expiration_notified=False,
        )

        self.stdout.write(f'Companies to check: {companies.count()}')

        for company in companies:
            if not company.plan_is_expiring_soon:
                continue
            try:
                if not company.email:
                    self.stdout.write(self.style.WARNING(f'{company.business_name}: no email configured, skipped'))
                    continue
                send_mail(
                    subject=f'Tu plan de facturación está por vencer - {company.business_name}',
                    message=(
                        f'Hola {company.business_name},\n\n'
                        f'Tu plan de facturación "{company.plan.name}" vence el '
                        f'{company.plan_end_date.strftime("%d/%m/%Y")} '
                        f'(en {company.days_until_plan_expires} días).\n\n'
                        f'Por favor contáctanos para renovar tu plan y evitar interrupciones en el servicio.\n\n'
                        f'Saludos.'
                    ),
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[company.email],
                    fail_silently=False,
                )
                company.plan_expiration_notified = True
                company.save()
                self.stdout.write(self.style.SUCCESS(f'{company.business_name}: email sent to {company.email}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'{company.business_name}: error sending email: {e}'))

        self.stdout.write(self.style.SUCCESS('Process completed successfully'))

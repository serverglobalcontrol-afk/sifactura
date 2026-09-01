from datetime import datetime, timedelta

from django.core.management import BaseCommand
from django_tenants.utils import schema_context

from config import settings
from core.pos.models import Sale, CreditNote, INVOICE_STATUS, VOUCHER_TYPE
from core.pos.utilities.sri import SRI
from core.tenant.models import Company


class Command(BaseCommand):
    help = "Authorize electronic invoices and send them by email"

    def add_arguments(self, parser):
        parser.add_argument(
            '--start_date',
            type=str,
            default=None,
            help='Start date (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--end_date',
            type=str,
            default=None,
            help='End date (YYYY-MM-DD)'
        )

    def handle(self, *args, **options):
        sri = SRI()

        if options['start_date'] and options['end_date']:
            start_date = datetime.strptime(
                options['start_date'],
                '%Y-%m-%d'
            ).date()

            end_date = datetime.strptime(
                options['end_date'],
                '%Y-%m-%d'
            ).date()
        else:
            today = datetime.now().date()
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)

        self.stdout.write(
            self.style.SUCCESS(
                f'Processing documents from {start_date} to {end_date}'
            )
        )

        excluded_invoice_states = [
            INVOICE_STATUS[2][0],
            INVOICE_STATUS[3][0],
            INVOICE_STATUS[4][0]
        ]

        companies = Company.objects.exclude(
            scheme__schema_name=settings.DEFAULT_SCHEMA
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Companies found: {companies.count()}'
            )
        )

        for company in companies:
            self.stdout.write("")
            self.stdout.write("=" * 80)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Processing tenant: {company.scheme.schema_name}'
                )
            )

            with schema_context(company.scheme.schema_name):

                sales = Sale.objects.filter(
                    date_joined__range=[start_date, end_date],
                    receipt__voucher_type=VOUCHER_TYPE[0][0],
                    create_electronic_invoice=False
                ).exclude(
                    status__in=excluded_invoice_states
                )

                self.stdout.write(
                    f'Sales found: {sales.count()}'
                )

                for index, instance in enumerate(sales, start=1):
                    try:
                        self.stdout.write(
                            f'[{index}/{sales.count()}] '
                            f'Sale #{instance.pk} '
                            f'Status: {instance.status}'
                        )

                        if instance.status == INVOICE_STATUS[0][0]:
                            self.stdout.write(
                                f'Generating electronic invoice: {instance.pk}'
                            )
                            instance.generate_electronic_invoice()

                        elif instance.status == INVOICE_STATUS[1][0]:
                            self.stdout.write(
                                f'Sending email: {instance.pk}'
                            )
                            sri.notify_by_email(
                                instance=instance,
                                company=instance.company,
                                client=instance.client
                            )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Error processing sale {instance.pk}: {e}'
                            )
                        )

                credit_notes = CreditNote.objects.filter(
                    date_joined__range=[start_date, end_date],
                    create_electronic_invoice=False
                ).exclude(
                    status__in=excluded_invoice_states
                )

                self.stdout.write(
                    f'Credit notes found: {credit_notes.count()}'
                )

                for index, instance in enumerate(credit_notes, start=1):
                    try:
                        self.stdout.write(
                            f'[{index}/{credit_notes.count()}] '
                            f'Credit Note #{instance.pk} '
                            f'Status: {instance.status}'
                        )

                        if instance.status == INVOICE_STATUS[0][0]:
                            self.stdout.write(
                                f'Generating credit note: {instance.pk}'
                            )
                            instance.generate_electronic_invoice()

                        elif instance.status == INVOICE_STATUS[1][0]:
                            self.stdout.write(
                                f'Sending email: {instance.pk}'
                            )
                            sri.notify_by_email(
                                instance=instance,
                                company=instance.company,
                                client=instance.sale.client
                            )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Error processing credit note {instance.pk}: {e}'
                            )
                        )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                'Process completed successfully'
            )
        )

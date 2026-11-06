from django.conf import settings
from django.db import migrations

# Campos que eran DateField y pasaron a DateTimeField (migraciones 0023 y 0024):
# Postgres convirtió cada fecha a medianoche UTC, que en Guayaquil es las 19:00
# del día anterior. Se llevan a la medianoche local del mismo día, que es lo que
# la fecha significaba. Solo se tocan filas a las 00:00:00.000000 UTC exactas, así
# que repetirla no cambia nada y los registros nuevos (con hora real) quedan igual.
FIELDS = [
    ('creditnote', 'date_joined'),
    ('ctascollect', 'date_joined'),
    ('debtspay', 'date_joined'),
    ('expenses', 'date_joined'),
    ('paymentsctacollect', 'date_joined'),
    ('paymentsdebtspay', 'date_joined'),
    ('purchase', 'date_joined'),
    ('sale', 'authorization_date'),
]


def midnight_utc_to_local(apps, schema_editor):
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for model_name, field_name in FIELDS:
            model = apps.get_model('pos', model_name)
            table = quote(model._meta.db_table)
            column = quote(model._meta.get_field(field_name).column)
            cursor.execute(
                f"UPDATE {table} "
                f"SET {column} = (({column} AT TIME ZONE 'UTC')::date)::timestamp AT TIME ZONE %s "
                f"WHERE ({column} AT TIME ZONE 'UTC')::time = '00:00:00'",
                [settings.TIME_ZONE],
            )


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0041_pdf_authorized_max_length'),
    ]

    operations = [
        migrations.RunPython(midnight_utc_to_local, migrations.RunPython.noop),
    ]

from django.db import migrations

from core.pos.retention_catalog import seed_retention_concepts


def seed(apps, schema_editor):
    """Siembra el catálogo oficial de conceptos de retención en cada schema.
    No pisa lo que la empresa ya haya ajustado (get_or_create)."""
    seed_retention_concepts(apps.get_model('pos', 'RetentionConcept'))


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0037_supplier_retention'),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]

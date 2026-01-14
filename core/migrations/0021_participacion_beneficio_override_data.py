from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0020_documentoinversor"),
    ]

    operations = [
        migrations.AddField(
            model_name="participacion",
            name="beneficio_override_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Overrides detallados del beneficio (bruto, comisión, neto, retención, etc.)",
                null=True,
            ),
        ),
    ]

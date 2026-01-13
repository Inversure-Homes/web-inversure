from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_merge_20260113_1217"),
    ]

    operations = [
        migrations.AddField(
            model_name="participacion",
            name="beneficio_neto_override",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Beneficio neto del inversor para operaciones históricas (override manual)",
                max_digits=12,
                null=True,
            ),
        ),
    ]

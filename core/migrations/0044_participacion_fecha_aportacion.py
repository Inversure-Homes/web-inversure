from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_ingreso_justificante_pagado"),
    ]

    operations = [
        migrations.AddField(
            model_name="participacion",
            name="fecha_aportacion",
            field=models.DateField(blank=True, help_text="Fecha de la aportación para cálculo de rentabilidad", null=True),
        ),
    ]

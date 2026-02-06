from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0042_gasto_pagado"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingresoproyecto",
            name="pagado",
            field=models.BooleanField(
                default=False,
                help_text="Indica si el ingreso está cobrado",
            ),
        ),
        migrations.CreateModel(
            name="JustificanteIngreso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archivo", models.FileField(upload_to="justificantes_ingresos/%Y/%m/")),
                ("nombre_original", models.CharField(blank=True, max_length=255, null=True)),
                ("fecha_subida", models.DateTimeField(auto_now_add=True)),
                ("ingreso", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="justificante", to="core.ingresoproyecto")),
            ],
        ),
    ]

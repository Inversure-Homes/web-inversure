from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0023_update_proyecto_estado_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proyecto",
            name="estado",
            field=models.CharField(
                choices=[
                    ("captacion", "Captación"),
                    ("comprado", "Comprado"),
                    ("comercializacion", "Comercialización"),
                    ("reservado", "Reservado"),
                    ("vendido", "Vendido"),
                    ("cerrado", "Cerrado"),
                    ("descartado", "Descartado"),
                ],
                default="captacion",
                max_length=20,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_inversorperfil_proyectos_visibles"),
    ]

    operations = [
        migrations.AddField(
            model_name="inversorperfil",
            name="aportacion_inicial_override",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Ajuste manual de la aportación inicial para operaciones históricas",
                max_digits=12,
                null=True,
            ),
        ),
    ]

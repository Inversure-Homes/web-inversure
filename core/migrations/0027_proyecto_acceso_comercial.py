from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_inversorperfil_aportacion_inicial_override"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="acceso_comercial",
            field=models.BooleanField(
                default=False,
                help_text="Permite acceso del equipo comercial a este proyecto",
            ),
        ),
    ]

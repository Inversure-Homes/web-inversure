from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0028_proyecto_beneficio_estimado_base"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="mostrar_en_landing",
            field=models.BooleanField(
                default=False,
                help_text="Permite mostrar este proyecto en la landing pública",
            ),
        ),
    ]

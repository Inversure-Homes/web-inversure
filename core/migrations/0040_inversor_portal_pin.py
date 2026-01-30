from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0039_estudio_conversion_aprobacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="inversorperfil",
            name="portal_pin_hash",
            field=models.CharField(
                blank=True,
                default="",
                help_text="PIN de acceso al portal del inversor (hash)",
                max_length=128,
            ),
        ),
        migrations.AddField(
            model_name="inversorperfil",
            name="portal_pin_set_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Fecha de última actualización del PIN del portal",
                null=True,
            ),
        ),
    ]

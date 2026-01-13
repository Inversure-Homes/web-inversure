from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_documentoproyecto_tipo_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentoproyecto",
            name="es_principal",
            field=models.BooleanField(default=False),
        ),
    ]

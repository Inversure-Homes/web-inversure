from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_documento_proyecto"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentoproyecto",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("inmueble", "Documentación inmueble"),
                    ("facturas", "Facturas"),
                    ("fotografias", "Fotografías"),
                    ("otros", "Otros"),
                ],
                default="otros",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="documentoproyecto",
            name="titulo",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
    ]

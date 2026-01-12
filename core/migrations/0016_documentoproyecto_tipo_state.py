from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_documentoproyecto_categoria_titulo"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name="documentoproyecto",
                    name="tipo",
                    field=models.CharField(
                        choices=[
                            ("inmueble", "Documentación inmueble"),
                            ("facturas", "Facturas"),
                            ("fotografias", "Fotografías"),
                            ("otros", "Otros"),
                        ],
                        default="otros",
                        max_length=30,
                    ),
                ),
            ],
        ),
    ]

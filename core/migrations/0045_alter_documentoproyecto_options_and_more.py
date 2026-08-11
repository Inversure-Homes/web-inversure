from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_participacion_fecha_aportacion"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterModelOptions(
                    name="documentoproyecto",
                    options={"ordering": ["-creado", "-id"]},
                ),
                migrations.RemoveField(
                    model_name="documentoproyecto",
                    name="fecha_documento",
                ),
                migrations.RemoveField(
                    model_name="documentoproyecto",
                    name="nombre_original",
                ),
                migrations.RemoveField(
                    model_name="documentoproyecto",
                    name="observaciones",
                ),
                migrations.AlterField(
                    model_name="documentoproyecto",
                    name="archivo",
                    field=models.FileField(upload_to="proyectos/documentos/%Y/%m/"),
                ),
            ],
        ),
    ]

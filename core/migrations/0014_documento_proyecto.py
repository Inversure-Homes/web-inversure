from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_inversor_portal"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentoProyecto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("categoria", models.CharField(choices=[("inmueble", "Documentación inmueble"), ("facturas", "Facturas"), ("fotografias", "Fotografías"), ("otros", "Otros")], default="otros", max_length=20)),
                ("titulo", models.CharField(max_length=255)),
                ("archivo", models.FileField(upload_to="proyectos/documentos/%Y/%m/")),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("proyecto", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="documentos", to="core.proyecto")),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
    ]

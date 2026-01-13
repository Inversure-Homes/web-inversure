from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_participacion_beneficio_neto_override"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentoInversor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("categoria", models.CharField(choices=[("contrato", "Contrato"), ("retenciones", "Certificado retenciones"), ("comunicaciones", "Comunicaciones"), ("otros", "Otros")], default="otros", max_length=20)),
                ("titulo", models.CharField(max_length=255)),
                ("archivo", models.FileField(upload_to="inversores/documentos/%Y/%m/")),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
        migrations.AddField(
            model_name="documentoinversor",
            name="inversor",
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="documentos", to="core.inversorperfil"),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_participacion_estado"),
    ]

    operations = [
        migrations.CreateModel(
            name="InversorPerfil",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=64, unique=True)),
                ("activo", models.BooleanField(default=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("cliente", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="perfil_inversor", to="core.cliente")),
            ],
        ),
        migrations.CreateModel(
            name="SolicitudParticipacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("importe_solicitado", models.DecimalField(decimal_places=2, max_digits=12)),
                ("comentario", models.TextField(blank=True, null=True)),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada")], default="pendiente", max_length=12)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("inversor", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="solicitudes", to="core.inversorperfil")),
                ("proyecto", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="solicitudes_participacion", to="core.proyecto")),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ComunicacionInversor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=255)),
                ("mensaje", models.TextField()),
                ("leida", models.BooleanField(default=False)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("inversor", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="comunicaciones", to="core.inversorperfil")),
                ("proyecto", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="comunicaciones_inversores", to="core.proyecto")),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
    ]

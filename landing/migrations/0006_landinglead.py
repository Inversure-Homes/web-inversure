from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("landing", "0005_hero_etiqueta_hero_fondo_color_hero_fondo_imagen_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LandingLead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("inversor", "Inversor"), ("oportunidad", "Oportunidad")], max_length=20)),
                ("nombre", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=254)),
                ("telefono", models.CharField(blank=True, max_length=40)),
                ("capital", models.CharField(blank=True, max_length=120)),
                ("ubicacion", models.CharField(blank=True, max_length=200)),
                ("mensaje", models.TextField(blank=True)),
                ("origen_url", models.CharField(blank=True, max_length=300)),
                ("origen_ref", models.CharField(blank=True, max_length=300)),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-creado", "-id"],
            },
        ),
    ]

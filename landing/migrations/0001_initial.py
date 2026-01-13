from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Hero",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=200)),
                ("subtitulo", models.CharField(blank=True, max_length=300)),
                ("cta_texto", models.CharField(default="Acceder a la plataforma", max_length=80)),
                ("cta_url", models.CharField(default="/app/", max_length=200)),
                ("imagen", models.ImageField(blank=True, null=True, upload_to="landing/hero/")),
                ("activo", models.BooleanField(default=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-actualizado", "-id"]},
        ),
        migrations.CreateModel(
            name="Noticia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=220)),
                ("slug", models.SlugField(blank=True, max_length=240, unique=True)),
                ("extracto", models.TextField(blank=True)),
                ("cuerpo", models.TextField()),
                ("imagen", models.ImageField(blank=True, null=True, upload_to="landing/noticias/")),
                ("autor", models.CharField(blank=True, max_length=120)),
                ("fecha_publicacion", models.DateField(default=django.utils.timezone.now)),
                ("estado", models.CharField(choices=[("borrador", "Borrador"), ("publicado", "Publicado"), ("archivado", "Archivado")], default="borrador", max_length=20)),
                ("actualizado", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-fecha_publicacion", "-id"]},
        ),
        migrations.CreateModel(
            name="Seccion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=200)),
                ("texto", models.TextField(blank=True)),
                ("icono", models.CharField(blank=True, help_text="Nombre de icono Bootstrap (ej. bi-shield-lock).", max_length=60)),
                ("imagen", models.ImageField(blank=True, null=True, upload_to="landing/secciones/")),
                ("orden", models.PositiveIntegerField(default=0)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={"ordering": ["orden", "id"]},
        ),
    ]

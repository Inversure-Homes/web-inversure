from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("landing", "0002_seed_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MediaAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(blank=True, max_length=200)),
                ("archivo", models.ImageField(upload_to="landing/media/")),
                ("categoria", models.CharField(choices=[("general", "General"), ("landing", "Landing"), ("noticias", "Noticias")], default="general", max_length=20)),
                ("alt_texto", models.CharField(blank=True, max_length=200)),
                ("creado", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-creado", "-id"]},
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0035_estimado_real_importes"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentoproyecto",
            name="usar_pdf",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentoproyecto",
            name="usar_story",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentoproyecto",
            name="usar_instagram",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documentoproyecto",
            name="usar_dossier",
            field=models.BooleanField(default=False),
        ),
    ]

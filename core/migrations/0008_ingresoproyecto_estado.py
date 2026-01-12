from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_alter_estudio_datos"),
    ]

    operations = [
        migrations.AddField(
            model_name="ingresoproyecto",
            name="estado",
            field=models.CharField(
                choices=[("estimado", "Estimado"), ("confirmado", "Confirmado")],
                default="estimado",
                max_length=15,
            ),
        ),
    ]

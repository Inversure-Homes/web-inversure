from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_merge_0010s"),
    ]

    operations = [
        migrations.AddField(
            model_name="participacion",
            name="estado",
            field=models.CharField(
                choices=[("pendiente", "Pendiente"), ("confirmada", "Confirmada"), ("cancelada", "Cancelada")],
                default="pendiente",
                max_length=12,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_alter_proyecto_estado"),
    ]

    operations = [
        migrations.AddField(
            model_name="inversorperfil",
            name="proyectos_visibles",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="IDs de proyectos visibles en el portal del inversor",
                null=True,
            ),
        ),
    ]

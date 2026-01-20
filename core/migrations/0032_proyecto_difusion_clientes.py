from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0031_alter_documentoproyecto_categoria_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="difusion_clientes",
            field=models.ManyToManyField(
                blank=True,
                help_text="Clientes seleccionados para la difusión de este proyecto",
                related_name="proyectos_difusion",
                to="core.cliente",
            ),
        ),
    ]

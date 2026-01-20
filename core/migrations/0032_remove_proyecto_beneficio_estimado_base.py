from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0031_alter_documentoproyecto_categoria_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="proyecto",
            name="beneficio_estimado_base",
        ),
    ]

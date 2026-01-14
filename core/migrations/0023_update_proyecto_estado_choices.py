from django.db import migrations


def forwards(apps, schema_editor):
    Proyecto = apps.get_model("core", "Proyecto")
    mapping = {
        "estudio": "captacion",
        "operacion": "comprado",
    }
    for old, new in mapping.items():
        Proyecto.objects.filter(estado=old).update(estado=new)


def backwards(apps, schema_editor):
    Proyecto = apps.get_model("core", "Proyecto")
    mapping = {
        "captacion": "estudio",
        "comprado": "operacion",
    }
    for old, new in mapping.items():
        Proyecto.objects.filter(estado=old).update(estado=new)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0022_proyecto_codigo_proyecto"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

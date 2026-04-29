from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_inversor_portal"),
    ]

    operations = [
        # NOOP: en este repo `DocumentoProyecto` se creó ya en `0001_initial`.
        # Se mantiene esta migración para conservar el grafo histórico de dependencias.
    ]

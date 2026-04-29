from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_checklistitem"),
    ]

    operations = [
        # Este proyecto ya incluye el FK `gasto` en `0009_checklistitem`.
        # Esta migración se mantiene como NOOP para no romper instalaciones nuevas (SQLite)
        # ni el grafo de dependencias histórico (0011_merge_0010s).
    ]

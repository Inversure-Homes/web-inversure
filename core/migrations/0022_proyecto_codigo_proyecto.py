from django.db import migrations, models


def _backfill_codigo_proyecto(apps, schema_editor):
    Proyecto = apps.get_model("core", "Proyecto")
    max_codigo = (
        Proyecto.objects.exclude(codigo_proyecto__isnull=True)
        .aggregate(models.Max("codigo_proyecto"))
        .get("codigo_proyecto__max")
        or 0
    )
    current = int(max_codigo)
    for proyecto in Proyecto.objects.filter(codigo_proyecto__isnull=True).order_by("id"):
        current += 1
        proyecto.codigo_proyecto = current
        proyecto.save(update_fields=["codigo_proyecto"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0021_participacion_beneficio_override_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="codigo_proyecto",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Código interno visible del proyecto (contador propio)",
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(_backfill_codigo_proyecto, migrations.RunPython.noop),
    ]

from django.db import migrations, models
from django.db.models import F


def _seed_importes(apps, schema_editor):
    GastoProyecto = apps.get_model("core", "GastoProyecto")
    IngresoProyecto = apps.get_model("core", "IngresoProyecto")

    GastoProyecto.objects.filter(importe_estimado__isnull=True).update(importe_estimado=F("importe"))
    GastoProyecto.objects.filter(estado="confirmado", importe_real__isnull=True).update(importe_real=F("importe"))

    IngresoProyecto.objects.filter(importe_estimado__isnull=True).update(importe_estimado=F("importe"))
    IngresoProyecto.objects.filter(estado="confirmado", importe_real__isnull=True).update(importe_real=F("importe"))


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_documentoproyecto_factura_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="gastoproyecto",
            name="importe_estimado",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Importe estimado original", max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="gastoproyecto",
            name="importe_real",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Importe real confirmado", max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="ingresoproyecto",
            name="importe_estimado",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Importe estimado original", max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="ingresoproyecto",
            name="importe_real",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="Importe real confirmado", max_digits=12, null=True),
        ),
        migrations.RunPython(_seed_importes, migrations.RunPython.noop),
    ]

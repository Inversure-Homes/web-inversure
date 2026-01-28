from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_responsables_y_checklist_cierre"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="estudio",
            name="conversion_solicitada_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuario que solicitó la conversión a proyecto",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="estudios_conversion_solicitada",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="estudio",
            name="conversion_solicitada_en",
            field=models.DateTimeField(
                blank=True,
                help_text="Fecha/hora en que se solicitó la conversión a proyecto",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="estudio",
            name="conversion_aprobada_por",
            field=models.ForeignKey(
                blank=True,
                help_text="Administrador que aprobó la conversión a proyecto",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="estudios_conversion_aprobada",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="estudio",
            name="conversion_aprobada_en",
            field=models.DateTimeField(
                blank=True,
                help_text="Fecha/hora de aprobación de la conversión a proyecto",
                null=True,
            ),
        ),
    ]

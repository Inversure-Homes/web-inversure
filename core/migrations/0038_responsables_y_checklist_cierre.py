from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_inversor_push_subscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="responsable_user",
            field=models.ForeignKey(
                blank=True,
                help_text="Usuario responsable del proyecto",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proyectos_responsable",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="proyecto",
            name="responsable",
            field=models.CharField(
                blank=True,
                help_text="Nombre visible del responsable (compatibilidad)",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="checklistitem",
            name="responsable_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="checklist_items_asignados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="checklistitem",
            name="cerrado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="checklist_items_cerrados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="checklistitem",
            name="cerrado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_checklistitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="checklistitem",
            name="gasto",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="checklist_items",
                to="core.gastoproyecto",
            ),
        ),
    ]

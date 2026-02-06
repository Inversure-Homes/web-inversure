from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0041_encrypt_cliente_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="gastoproyecto",
            name="pagado",
            field=models.BooleanField(
                default=False,
                help_text="Indica si el gasto está pagado",
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccess",
            name="can_facturas_preview",
            field=models.BooleanField(default=False),
        ),
    ]

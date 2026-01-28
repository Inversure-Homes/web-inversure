from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_webpushsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="useraccess",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("administracion", "Administracion"),
                    ("direccion", "Direccion"),
                    ("comercial", "Comercial"),
                    ("marketing", "Marketing"),
                ],
                default="",
                help_text="Rol principal del usuario",
                max_length=20,
            ),
        ),
    ]

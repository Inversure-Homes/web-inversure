from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_documentoproyecto_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="InversorPushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.URLField(unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.CharField(blank=True, default="", max_length=500)),
                ("is_active", models.BooleanField(default=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "inversor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_subscriptions",
                        to="core.inversorperfil",
                    ),
                ),
            ],
            options={
                "ordering": ["-actualizado", "-creado", "-id"],
            },
        ),
    ]

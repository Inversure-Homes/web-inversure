from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_usersession_and_connectionlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebPushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("endpoint", models.TextField(unique=True)),
                ("p256dh", models.CharField(max_length=255)),
                ("auth", models.CharField(max_length=255)),
                ("user_agent", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="push_subscriptions", to="auth.user")),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
    ]

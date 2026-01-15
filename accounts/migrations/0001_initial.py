from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("use_custom_perms", models.BooleanField(default=False, help_text="Si está activo, se usan los permisos individuales y se ignoran los roles.")),
                ("can_simulador", models.BooleanField(default=False)),
                ("can_estudios", models.BooleanField(default=False)),
                ("can_proyectos", models.BooleanField(default=False)),
                ("can_clientes", models.BooleanField(default=False)),
                ("can_inversores", models.BooleanField(default=False)),
                ("can_usuarios", models.BooleanField(default=False)),
                ("can_cms", models.BooleanField(default=False)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="user_access", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

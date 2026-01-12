from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_ingresoproyecto_estado"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChecklistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fase", models.CharField(choices=[("compra", "Compra"), ("post_compra", "Post-compra"), ("operacion", "Operación"), ("venta", "Venta"), ("post_venta", "Post-venta")], default="compra", max_length=20)),
                ("titulo", models.CharField(max_length=255)),
                ("descripcion", models.TextField(blank=True, null=True)),
                ("responsable", models.CharField(blank=True, max_length=255, null=True)),
                ("fecha_objetivo", models.DateField(blank=True, null=True)),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("en_curso", "En curso"), ("hecho", "Hecho")], default="pendiente", max_length=15)),
                ("coste_estimado", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("coste_real", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("gasto", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="checklist_items", to="core.gastoproyecto")),
                ("proyecto", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="checklist_items", to="core.proyecto")),
            ],
            options={
                "ordering": ["fase", "fecha_objetivo", "id"],
            },
        ),
    ]

from django.db import migrations
from django.utils.timezone import now


def seed_landing(apps, schema_editor):
    Hero = apps.get_model("landing", "Hero")
    Seccion = apps.get_model("landing", "Seccion")
    Noticia = apps.get_model("landing", "Noticia")

    if not Hero.objects.exists():
        Hero.objects.create(
            titulo="Trazabilidad real para cada operacion inmobiliaria",
            subtitulo="Controla cada fase con datos claros, documentos centralizados y transparencia para inversores.",
            cta_texto="Acceso a la plataforma",
            cta_url="/app/login/",
            activo=True,
        )

    if not Seccion.objects.exists():
        Seccion.objects.bulk_create(
            [
                Seccion(
                    titulo="Control de inversion",
                    texto="Seguimiento completo de capital, gastos y rentabilidad en tiempo real.",
                    icono="bi-shield-check",
                    orden=1,
                    activo=True,
                ),
                Seccion(
                    titulo="Memoria economica",
                    texto="Registro auditado de ingresos y gastos, con estimados y reales.",
                    icono="bi-journal-bookmark",
                    orden=2,
                    activo=True,
                ),
                Seccion(
                    titulo="Comunicacion con inversores",
                    texto="Actualizaciones claras del estado de cada proyecto y su progreso.",
                    icono="bi-graph-up-arrow",
                    orden=3,
                    activo=True,
                ),
            ]
        )

    if not Noticia.objects.exists():
        Noticia.objects.create(
            titulo="Inversure Homes lanza su panel de trazabilidad",
            extracto="La plataforma unifica documentos, metricas y decisiones en una sola vista para el inversor.",
            cuerpo="Presentamos la primera version del panel de trazabilidad para operaciones inmobiliarias. "
                   "Nuestro objetivo es ofrecer transparencia total en cada fase del proyecto.",
            autor="Equipo Inversure",
            fecha_publicacion=now().date(),
            estado="publicado",
        )


def unseed_landing(apps, schema_editor):
    Hero = apps.get_model("landing", "Hero")
    Seccion = apps.get_model("landing", "Seccion")
    Noticia = apps.get_model("landing", "Noticia")
    Hero.objects.all().delete()
    Seccion.objects.all().delete()
    Noticia.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("landing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_landing, reverse_code=unseed_landing),
    ]

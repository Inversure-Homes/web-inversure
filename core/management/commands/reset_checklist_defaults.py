from django.core.management.base import BaseCommand

from core.models import ChecklistItem, Proyecto
from core.views import _checklist_defaults


class Command(BaseCommand):
    help = "Reinicia el checklist operativo para todos los proyectos."

    def handle(self, *args, **options):
        proyectos = list(Proyecto.objects.all())
        total_items = ChecklistItem.objects.count()
        ChecklistItem.objects.all().delete()

        nuevos = []
        defaults = _checklist_defaults()
        for proyecto in proyectos:
            for fase, titulo in defaults:
                nuevos.append(
                    ChecklistItem(
                        proyecto=proyecto,
                        fase=fase,
                        titulo=titulo,
                        estado="pendiente",
                    )
                )

        ChecklistItem.objects.bulk_create(nuevos)

        self.stdout.write(
            self.style.SUCCESS(
                f"Checklist reiniciado. Proyectos: {len(proyectos)}. "
                f"Items borrados: {total_items}. Items creados: {len(nuevos)}."
            )
        )

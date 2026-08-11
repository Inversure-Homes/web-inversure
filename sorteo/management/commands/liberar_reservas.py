from django.core.management.base import BaseCommand

from sorteo.services import liberar_caducadas


class Command(BaseCommand):
    help = (
        "Devuelve a la venta las participaciones cuya reserva ha caducado. "
        "Pensado para un cron cada pocos minutos: sin él, las papeletas de "
        "quien no termina de pagar solo se liberan cuando alguien visita la web."
    )

    def handle(self, *args, **options):
        liberadas = liberar_caducadas()
        self.stdout.write(
            self.style.SUCCESS("Participaciones liberadas: {}".format(liberadas))
        )

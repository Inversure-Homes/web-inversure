"""
Correos de la firma de contratos.

El código de un solo uso es lo que acredita que quien firma controla esa cuenta
de correo, así que este envío no es un adorno: es la mitad de la prueba. Si
falla, no se puede firmar, y así se le dice al usuario en lugar de dejarle
esperando.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

log = logging.getLogger(__name__)


def enviar_codigo_contrato(participacion, email: str, codigo: str) -> bool:
    """El código de verificación. Falla ruidosamente: sin él no hay firma."""
    cuerpo = (
        "Hola{}:\n\n"
        "Tu código para firmar el contrato de {} es:\n\n"
        "        {}\n\n"
        "Caduca en 15 minutos y solo sirve una vez.\n\n"
        "Si no has sido tú quien lo ha pedido, ignora este mensaje y avísanos: "
        "sin este código nadie puede firmar en tu nombre.\n\n"
        "{}\n"
    ).format(
        " " + (participacion.cliente.nombre or "").split()[0] if participacion.cliente.nombre else "",
        participacion.proyecto.nombre,
        codigo,
        settings.PRESTATARIA["razon_social"],
    )
    try:
        EmailMessage(
            subject="Tu código para firmar el contrato",
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        ).send(fail_silently=False)
        return True
    except Exception:
        log.exception("No se pudo enviar el código de firma a %s", email)
        return False


def enviar_contrato_firmado(participacion, email: str, pdf: bytes) -> bool:
    """
    La copia firmada, al firmante.

    Aquí sí se traga el error: el contrato ya está firmado y guardado, y no
    tumbamos una firma válida porque el correo no salga. Queda en el log.
    """
    cuerpo = (
        "Hola:\n\n"
        "Adjuntamos tu contrato firmado de {}.\n\n"
        "Incluye una hoja final con las evidencias de la firma: la huella "
        "digital del documento, la fecha y hora, y el correo verificado. "
        "Consérvalo.\n\n"
        "{}\n"
    ).format(participacion.proyecto.nombre, settings.PRESTATARIA["razon_social"])
    try:
        mensaje = EmailMessage(
            subject="Tu contrato firmado · {}".format(participacion.proyecto.nombre),
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )
        mensaje.attach("contrato-firmado.pdf", pdf, "application/pdf")
        mensaje.send(fail_silently=False)
        return True
    except Exception:
        log.exception("No se pudo enviar el contrato firmado a %s", email)
        return False

"""
Correos del sorteo.

Usan la configuración SMTP que ya tiene el proyecto. En desarrollo, con
`EMAIL_BACKEND` de consola, se imprimen por pantalla en lugar de enviarse.

Ningún fallo de correo debe tumbar la operación que lo dispara: un pago
confirmado sigue siendo válido aunque el email no salga.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

log = logging.getLogger(__name__)


def base_url():
    url = getattr(settings, "WAGTAILADMIN_BASE_URL", "") or ""
    return url.rstrip("/") or "https://inversurehomes.es"


def _enviar(asunto, plantilla, contexto, destinatario):
    try:
        cuerpo = render_to_string(plantilla, contexto)
        mensaje = EmailMultiAlternatives(
            subject=asunto,
            body=cuerpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario],
        )
        mensaje.send(fail_silently=False)
        return True
    except Exception:
        log.exception("No se pudo enviar %s a %s", plantilla, destinatario)
        return False


def confirmar_alta(interesado):
    """Acuse de la lista de espera, con el enlace de baja obligatorio."""
    return _enviar(
        "Te avisaremos · {}".format(interesado.sorteo.titulo if interesado.sorteo else "Sorteo"),
        "sorteo/email/alta.txt",
        {
            "interesado": interesado,
            "sorteo": interesado.sorteo,
            "url_baja": base_url() + reverse("sorteo:baja", args=[interesado.token_baja]),
        },
        interesado.email,
    )


def confirmar_pedido(pedido):
    """
    Justificante de participación.

    Lleva los datos que la normativa exige en el soporte: número total emitido,
    precio y plazo de caducidad del premio.
    """
    return _enviar(
        "Tus participaciones · {}".format(pedido.sorteo.titulo),
        "sorteo/email/pedido.txt",
        {
            "pedido": pedido,
            "sorteo": pedido.sorteo,
            "url_pedido": base_url() + reverse("sorteo:pedido", args=[pedido.id]),
            "url_bases": base_url() + reverse("sorteo:bases"),
        },
        pedido.email,
    )


def avisar_ganador(acta):
    """Aviso a la persona premiada. El resto de condiciones van en las bases."""
    if not acta.pedido:
        return False
    return _enviar(
        "Tu participación ha resultado premiada · {}".format(acta.sorteo.titulo),
        "sorteo/email/ganador.txt",
        {
            "acta": acta,
            "sorteo": acta.sorteo,
            "pedido": acta.pedido,
            "url_bases": base_url() + reverse("sorteo:bases"),
        },
        acta.pedido.email,
    )


def reenviar_participaciones(email, sorteo, pedidos):
    """
    Devuelve al comprador los enlaces de sus participaciones.

    Solo se manda al correo con el que se compró, nunca a otro: es la única
    dirección que ya conocía esos enlaces, así que reenviarlos ahí no revela
    nada a nadie.
    """
    return _enviar(
        "Tus participaciones · {}".format(sorteo.titulo),
        "sorteo/email/recuperar.txt",
        {
            "sorteo": sorteo,
            "pedidos": [{"pedido": p, "url": base_url() + reverse("sorteo:pedido", args=[p.id])} for p in pedidos],
            "url_bases": base_url() + reverse("sorteo:bases"),
        },
        email,
    )

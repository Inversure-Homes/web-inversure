"""
Cierre de venta y relación certificada para el notario.

El notario no audita el sistema: extrae un número de entre las participaciones
que el organizador le presenta. Por eso lo que tiene que ser sólido no es el
sorteo —que hace él— sino **la relación de participaciones vendidas** que se le
entrega, y la prueba de que no se ha tocado después.

De ahí las dos piezas de este módulo:

1. `cerrar_venta` congela la venta y calcula una huella SHA-256 del listado
   definitivo. La huella se publica antes del sorteo, de modo que cualquiera
   —incluido el notario— puede recalcularla sobre el listado recibido y
   comprobar que es exactamente el mismo.
2. `relacion_certificada` genera el documento que se entrega, con esa huella
   impresa.
"""

import hashlib

from django.utils import timezone

from .models import Papeleta, Sorteo


def listado_canonico(sorteo):
    """
    Representación estable del listado de participaciones vendidas.

    Estable quiere decir que dos ejecuciones sobre los mismos datos producen
    byte a byte lo mismo: de eso depende que la huella sirva de algo. Por eso
    el orden es explícito y el formato, fijo.
    """
    filas = (
        Papeleta.objects.filter(sorteo=sorteo, estado=Papeleta.Estado.PAGADA)
        .select_related("pedido")
        .order_by("numero")
    )
    lineas = [
        "{};{};{}".format(
            p.numero,
            p.pedido.codigo if p.pedido else "",
            (p.pedido.nombre if p.pedido else "").strip(),
        )
        for p in filas
    ]
    return "\n".join(lineas), filas


def huella(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def cerrar_venta(sorteo):
    """
    Congela la venta y sella el listado.

    Irreversible a propósito: a partir de aquí el listado que se entrega al
    notario es el que es, y la huella lo demuestra.
    """
    if sorteo.cerrado_en:
        return sorteo

    texto, _ = listado_canonico(sorteo)
    Sorteo.objects.filter(pk=sorteo.pk).update(
        estado=Sorteo.Estado.CERRADO,
        cerrado_en=timezone.now(),
        hash_listado=huella(texto),
        participaciones_vendidas_cierre=len(texto.splitlines()) if texto else 0,
    )
    sorteo.refresh_from_db()
    return sorteo


def datos_relacion(sorteo):
    """Contexto del documento que se entrega al notario."""
    texto, filas = listado_canonico(sorteo)
    actual = huella(texto)
    return {
        "sorteo": sorteo,
        "filas": filas,
        "total": len(filas),
        "hash_actual": actual,
        "hash_cierre": sorteo.hash_listado,
        "coincide": (not sorteo.hash_listado) or actual == sorteo.hash_listado,
        "generado_en": timezone.now(),
    }

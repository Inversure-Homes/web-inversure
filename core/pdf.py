"""
Generación de PDF con WeasyPrint, con una sola configuración de fuentes por hilo.

WeasyPrint monta una `FontConfiguration` nueva en cada `write_pdf()` si no se le
pasa ninguna, y cada una crea su propio font map de Pango. Cuando el recolector
de basura libera esa configuración, Pango desmonta el font map y harfbuzz acaba
destruyendo caras de tipografía que ya no son válidas. El proceso se cae entero:

    pango_ft2_font_map_finalize → pango_fc_font_map_shutdown
        → hb_face_destroy → EXC_BAD_ACCESS

Se veía como una caída intermitente de la suite —una de cada doce— siempre
mientras corría el recolector, y eso despistaba: el GC era el momento en que
estallaba, no la causa. Lo dejó claro el informe de caída de macOS.

Compartir una configuración que no se destruye nunca evita esa ruta por
completo, y de paso ahorra rehacer en cada PDF un trabajo que es caro.

Se guarda una por hilo, no una para todo el proceso, porque Pango y fontconfig
no prometen ser seguros entre hilos. Y se conserva además una referencia fuerte
aparte para que no la recoja el recolector cuando muera el hilo que la creó:
que la configuración sobreviva es justo lo que evita la caída.
"""

import logging
import threading

log = logging.getLogger(__name__)

_local = threading.local()
_vivas = []  # referencias fuertes; que ninguna se llegue a finalizar nunca
_cerrojo = threading.Lock()

_SIN_CONFIGURACION = object()


def _configuracion_fuentes():
    """La configuración de fuentes de este hilo, creada una sola vez."""
    config = getattr(_local, "config", None)
    if config is not None:
        return None if config is _SIN_CONFIGURACION else config

    try:
        from weasyprint.text.fonts import FontConfiguration
    except Exception:
        # Ocurre cuando los tests sustituyen `weasyprint` por un doble sin
        # submódulos. Se anota una vez y se sigue sin ella: perder la mejora
        # es mucho menos grave que no poder generar el documento.
        log.warning(
            "Sin FontConfiguration de WeasyPrint: los PDF se generarán sin compartirla",
            exc_info=True,
        )
        _local.config = _SIN_CONFIGURACION
        return None

    config = FontConfiguration()
    _local.config = config
    with _cerrojo:
        _vivas.append(config)
    return config


def render_pdf(html: str, base_url: str | None = None) -> bytes:
    """El PDF de un HTML ya renderizado."""
    from weasyprint import HTML  # defer import: necesita pango y cairo

    documento = HTML(string=html, base_url=base_url)
    config = _configuracion_fuentes()
    if config is None:
        return documento.write_pdf()
    return documento.write_pdf(font_config=config)

"""
Contexto global mínimo para la web pública.

Existe por un motivo concreto: el enlace del pie no debe aparecer si no hay
ningún sorteo publicado, porque llevaría a un 404. Al desplegar por primera
vez la base de datos está vacía, así que el caso no es hipotético.
"""

from django.core.cache import cache

from .models import Sorteo

CLAVE = "sorteo_publicado"


def sorteo_publicado(request):
    """
    ¿Hay algún sorteo que enseñar?

    Se cachea un minuto: es una consulta en cada página de la landing, y la
    respuesta cambia como mucho una vez al año.
    """
    valor = cache.get(CLAVE)
    if valor is None:
        valor = Sorteo.objects.exists()
        cache.set(CLAVE, valor, 60)
    return {"hay_sorteo": valor}

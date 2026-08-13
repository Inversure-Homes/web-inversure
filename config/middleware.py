import os

from django.shortcuts import redirect
from django.urls import reverse


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.getenv("MAINTENANCE_MODE") == "1":
            maintenance_path = reverse("landing:maintenance")
            allowed_prefixes = (
                maintenance_path,
                "/healthz/",
                "/admin/",
                "/cms/",
                "/documents/",
                "/app/",
                "/static/",
            )
            if request.path.startswith(allowed_prefixes):
                return self.get_response(request)
            user = getattr(request, "user", None)
            if getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False):
                return self.get_response(request)
            return redirect(maintenance_path)
        return self.get_response(request)


class CabecerasSeguridadMiddleware:
    """
    Cabeceras que Django no trae de serie.

    La `Content-Security-Policy` va deliberadamente incompleta: no fija
    `script-src` ni `style-src`. Veintiocho plantillas del ERP llevan scripts y
    estilos en línea, así que una política estricta las rompería, y una CSP con
    `'unsafe-inline'` no protege de nada mientras da la impresión contraria.

    Lo que sí se puede cerrar hoy, se cierra: nadie puede embeber la aplicación
    en un marco, no se cargan plugins, no se puede reescribir la base de las
    URLs relativas y los formularios sólo pueden enviarse al propio dominio
    —que es lo que impide que un formulario inyectado mande los datos fuera—.

    Añadir `script-src` exige antes quitar el código en línea de esas
    plantillas. Está anotado como trabajo pendiente, no olvidado.
    """

    POLITICA = "; ".join([
        "default-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        # Las fotos de proyecto se sirven firmadas desde S3.
        "img-src 'self' data: https://inversure-docs.s3.amazonaws.com",
        "font-src 'self'",
        "upgrade-insecure-requests",
    ])

    # Ninguna de estas capacidades se usa; se apagan para que no se puedan pedir.
    PERMISOS = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.setdefault("Content-Security-Policy", self.POLITICA)
        respuesta.setdefault("Permissions-Policy", self.PERMISOS)
        return respuesta

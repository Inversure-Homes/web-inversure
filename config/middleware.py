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
                "/admin/",
                "/cms/",
                "/documents/",
                "/app/",
                "/static/",
            )
            if request.path.startswith(allowed_prefixes):
                return self.get_response(request)
            if request.user.is_authenticated:
                return self.get_response(request)
            return redirect(maintenance_path)
        return self.get_response(request)

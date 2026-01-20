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
            user = getattr(request, "user", None)
            if getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False):
                return self.get_response(request)
            return redirect(maintenance_path)
        return self.get_response(request)

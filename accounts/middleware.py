from django.shortcuts import redirect
from django.utils.http import urlencode

from .utils import resolve_permissions, use_custom_permissions, is_admin_user


class RoleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or "/"

        if path.startswith(("/static/", "/media/")):
            return self.get_response(request)

        is_app_path = path.startswith("/app/")
        is_wagtail_path = path.startswith("/cms/") or path.startswith("/documents/")
        is_admin_path = path.startswith("/admin/")

        is_public_app = path.startswith("/app/login/") or path.startswith("/app/logout/") or path.startswith("/app/inversor/")

        if is_app_path or is_wagtail_path or is_admin_path:
            if is_public_app:
                return self.get_response(request)

            user = request.user
            if not user.is_authenticated:
                qs = urlencode({"next": path})
                return redirect(f"/app/login/?{qs}")

            perms = resolve_permissions(user)

            if is_admin_path:
                if not is_admin_user(user):
                    return redirect("/app/")
                return self.get_response(request)

            if is_wagtail_path:
                if not perms.get("can_cms"):
                    return redirect("/app/")
                return self.get_response(request)

            if is_app_path:
                if perms.get("can_cms") and not any(
                    perms.get(k)
                    for k in (
                        "can_simulador",
                        "can_estudios",
                        "can_proyectos",
                        "can_clientes",
                        "can_inversores",
                        "can_usuarios",
                    )
                ):
                    return redirect("/cms/")
                if not any(
                    perms.get(k)
                    for k in (
                        "can_simulador",
                        "can_estudios",
                        "can_proyectos",
                        "can_clientes",
                        "can_inversores",
                        "can_usuarios",
                    )
                ):
                    return redirect("/app/login/")
                if not is_admin_user(user) and not use_custom_permissions(user):
                    if path.startswith("/app/simulador") and not perms.get("can_simulador"):
                        return redirect("/app/")
                    if path.startswith("/app/estudios") and not perms.get("can_estudios"):
                        return redirect("/app/")
                    if path.startswith("/app/proyectos") and not perms.get("can_proyectos"):
                        return redirect("/app/")
                    if path.startswith("/app/clientes") and not perms.get("can_clientes"):
                        return redirect("/app/")
                    if path.startswith("/app/inversores") and not perms.get("can_inversores"):
                        return redirect("/app/")
                    if path.startswith("/app/usuarios") and not perms.get("can_usuarios"):
                        return redirect("/app/")
                if use_custom_permissions(user):
                    if path.startswith("/app/simulador") and not perms.get("can_simulador"):
                        return redirect("/app/")
                    if path.startswith("/app/estudios") and not perms.get("can_estudios"):
                        return redirect("/app/")
                    if path.startswith("/app/proyectos") and not perms.get("can_proyectos"):
                        return redirect("/app/")
                    if path.startswith("/app/clientes") and not perms.get("can_clientes"):
                        return redirect("/app/")
                    if path.startswith("/app/inversores") and not perms.get("can_inversores"):
                        return redirect("/app/")
                    if path.startswith("/app/usuarios") and not perms.get("can_usuarios"):
                        return redirect("/app/")

        return self.get_response(request)

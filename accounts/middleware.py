from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from .models import UserSession
from .utils import resolve_permissions, use_custom_permissions, is_admin_user


def _get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class UserSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or "/"
        if path.startswith(("/static/", "/media/")):
            return self.get_response(request)

        if request.user.is_authenticated:
            if not request.session.session_key:
                request.session.save()
            session_key = request.session.session_key
            ip_address = _get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            session, _ = UserSession.objects.get_or_create(
                session_key=session_key,
                defaults={
                    "user": request.user,
                    "ip_address": ip_address,
                    "user_agent": user_agent[:512],
                },
            )
            if session.user_id != request.user.id:
                session.user = request.user
            if session.ip_address != ip_address:
                session.ip_address = ip_address
            if session.user_agent != user_agent[:512]:
                session.user_agent = user_agent[:512]
            now = timezone.now()
            if session.last_seen_at <= now - timezone.timedelta(seconds=60):
                session.last_seen_at = now
            if session.ended_at:
                session.ended_at = None
            session.save(update_fields=["user", "ip_address", "user_agent", "last_seen_at", "ended_at"])

        return self.get_response(request)


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
            try:
                is_verified = user.is_verified()
            except Exception:
                is_verified = False
            if not is_verified:
                setup_url = reverse("two_factor:setup")
                if not path.startswith(setup_url):
                    return redirect(setup_url)

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

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .middleware import _get_client_ip
from django.utils import timezone

from .models import UserConnectionLog, UserSession


@receiver(user_logged_in)
def _log_login(sender, request, user, **kwargs):
    UserConnectionLog.objects.create(
        user=user,
        event=UserConnectionLog.EVENT_LOGIN,
        ip_address=_get_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:512]),
    )
    if request.session.session_key:
        UserSession.objects.filter(session_key=request.session.session_key).update(ended_at=None)


@receiver(user_logged_out)
def _log_logout(sender, request, user, **kwargs):
    if not user:
        return
    UserConnectionLog.objects.create(
        user=user,
        event=UserConnectionLog.EVENT_LOGOUT,
        ip_address=_get_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:512]),
    )
    if request.session.session_key:
        UserSession.objects.filter(session_key=request.session.session_key).update(ended_at=timezone.now())

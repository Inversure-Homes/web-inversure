import json
import logging

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.conf import settings

from auditlog.models import LogEntry
from pywebpush import webpush, WebPushException

from .forms import UserCreateForm, UserEditForm
from .models import UserConnectionLog, UserSession, WebPushSubscription
from .utils import is_admin_user


def _is_admin(user):
    return is_admin_user(user)


def login_view(request):
    return redirect(reverse("two_factor:login"))


def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@login_required
@user_passes_test(_is_admin)
def users_list(request):
    usuarios = User.objects.order_by("username")
    grupos = Group.objects.order_by("name")
    return render(request, "accounts/users_list.html", {"usuarios": usuarios, "grupos": grupos})


@login_required
@user_passes_test(_is_admin)
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("accounts:users_list")
    else:
        form = UserCreateForm()
    return render(request, "accounts/user_form.html", {"form": form, "modo": "nuevo"})


@login_required
@user_passes_test(_is_admin)
def user_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            return redirect("accounts:users_list")
    else:
        form = UserEditForm(instance=user_obj)
    return render(request, "accounts/user_form.html", {"form": form, "modo": "editar", "user_obj": user_obj})


@login_required
@user_passes_test(_is_admin)
def user_delete(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        user_obj.delete()
        return redirect("accounts:users_list")
    return render(request, "accounts/confirm_delete.html", {"user_obj": user_obj})


@login_required
@user_passes_test(_is_admin)
def activity_dashboard(request):
    now = timezone.now()
    active_cutoff = now - timezone.timedelta(minutes=15)

    sessions = (
        UserSession.objects.select_related("user")
        .filter(last_seen_at__gte=active_cutoff, ended_at__isnull=True)
        .order_by("-last_seen_at")
    )
    recent_connections = UserConnectionLog.objects.select_related("user")[:100]
    recent_changes = LogEntry.objects.select_related("actor", "content_type")[:100]

    return render(
        request,
        "accounts/activity_dashboard.html",
        {
            "sessions": sessions,
            "recent_connections": recent_connections,
            "recent_changes": recent_changes,
            "active_cutoff_minutes": 15,
        },
    )


@login_required
@require_GET
def push_public_key(request):
    if not settings.VAPID_PUBLIC_KEY:
        return JsonResponse({"ok": False, "error": "VAPID public key missing"}, status=500)
    return JsonResponse({"ok": True, "publicKey": settings.VAPID_PUBLIC_KEY})


@login_required
@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = {}
    subscription = data.get("subscription") if isinstance(data, dict) else {}
    if not subscription:
        subscription = data if isinstance(data, dict) else {}
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not endpoint or not p256dh or not auth:
        return JsonResponse({"ok": False, "error": "Subscription incomplete"}, status=400)

    WebPushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500],
            "is_active": True,
        },
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = {}
    endpoint = data.get("endpoint")
    if not endpoint:
        return JsonResponse({"ok": False, "error": "Endpoint missing"}, status=400)
    WebPushSubscription.objects.filter(endpoint=endpoint, user=request.user).update(is_active=False)
    return JsonResponse({"ok": True})


def _webpush_send(subscription: WebPushSubscription, payload: dict) -> bool:
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        return False
    sub_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    try:
        webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
        )
        return True
    except WebPushException:
        logging.getLogger(__name__).exception("WebPush failed")
        return False


@login_required
@user_passes_test(_is_admin)
@require_POST
def push_send_test(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = {}
    title = (data.get("title") or "Inversure").strip()
    body = (data.get("body") or "Notificación de prueba.").strip()
    url = (data.get("url") or "/app/").strip()

    subs = WebPushSubscription.objects.filter(user=request.user, is_active=True)
    if not subs.exists():
        return JsonResponse({"ok": False, "error": "No active subscriptions"}, status=400)

    payload = {"title": title, "body": body, "url": url}
    sent = 0
    for sub in subs:
        if _webpush_send(sub, payload):
            sent += 1
    return JsonResponse({"ok": True, "sent": sent})

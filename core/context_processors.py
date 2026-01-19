from .models import SolicitudParticipacion


def pending_solicitudes(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        count = SolicitudParticipacion.objects.filter(estado="pendiente").count()
    except Exception:
        count = 0
    return {"pending_solicitudes_count": count}

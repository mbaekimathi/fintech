from accounts.models import AuditEvent


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def write_audit(request, action: str, *, object_type: str = "", object_id: str = "", detail: dict | None = None):
    actor = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id else "",
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        detail=detail or {},
    )

"""In-app notification helpers + phone tray Web Push."""

from __future__ import annotations

from accounts.models import User
from core.models import Notification
from core.webpush import send_web_push_to_user
from paybill.models import MoneyRequest

REVIEW_ROLES = (
    User.Role.ADMIN,
    User.Role.MANAGER,
    User.Role.ACCOUNTS,
    User.Role.IT_SUPPORT,
)


def review_recipients():
    qs = (
        User.objects.filter(is_active=True, is_approved=True)
        .exclude(role__in=[User.Role.PENDING_APPROVAL, User.Role.CLIENT])
        .select_related("permissions")
    )
    return [user for user in qs if user.can_review_requests()]


def notify_money_request_submitted(money_request: MoneyRequest) -> int:
    requester = money_request.requester
    name = requester.get_full_name() or requester.staff_code
    dest = money_request.get_destination_type_display()
    title = f"{name} requested KES {money_request.amount:,.2f}"
    recipient = (money_request.recipient_name or "").strip()
    body = f"{dest} · {money_request.destination}"
    if recipient:
        body = f"{body} ({recipient})"
    if money_request.account_ref:
        body = f"{body} / {money_request.account_ref}"
    url = "/paybill/transactions/"
    count = 0
    for user in review_recipients():
        if user.pk == requester.pk:
            continue
        Notification.objects.create(
            recipient=user,
            actor=requester,
            kind=Notification.Kind.MONEY_REQUEST,
            title=title[:160],
            body=body[:255],
            money_request=money_request,
        )
        send_web_push_to_user(user, title=title, body=body, url=url)
        count += 1
    return count


def notify_money_request_result(money_request: MoneyRequest, *, actor=None) -> Notification | None:
    requester = money_request.requester
    if not requester or not requester.pk:
        return None
    status = money_request.get_status_display()
    title = f"Request {status.lower()}: KES {money_request.amount:,.2f}"
    body = f"{money_request.get_destination_type_display()} · {money_request.destination}"
    note = Notification.objects.create(
        recipient=requester,
        actor=actor,
        kind=Notification.Kind.MONEY_REQUEST_RESULT,
        title=title[:160],
        body=body[:255],
        money_request=money_request,
    )
    send_web_push_to_user(requester, title=title, body=body, url="/")
    return note


def mark_money_request_notifications_read(money_request: MoneyRequest) -> int:
    """Mark every reviewer's copy for this request as read (request is resolved)."""
    return Notification.objects.filter(
        money_request=money_request,
        kind=Notification.Kind.MONEY_REQUEST,
        is_read=False,
    ).update(is_read=True)


def mark_notification_read(notification: Notification) -> None:
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])


def _session_user_id(user) -> int | None:
    if not user or not getattr(user, "is_authenticated", False):
        return None
    pk = getattr(user, "pk", None)
    return int(pk) if pk else None


def notifications_for_session_user(user):
    """
    Notifications visible to the authenticated session user only.

    Rows are always scoped to recipient=user. Kind is further limited by the
    effective role in this request (so a role-switched session does not show
    another workspace's review queue).
    """
    user_id = _session_user_id(user)
    if user_id is None:
        return Notification.objects.none()

    qs = Notification.objects.filter(recipient_id=user_id)
    role = getattr(user, "effective_role", None) or getattr(user, "role", None)
    if role in REVIEW_ROLES or (
        getattr(user, "is_superuser", False) and not getattr(user, "is_role_switched", False)
    ):
        return qs
    # Employees and other non-review sessions only see their own result updates.
    return qs.filter(kind=Notification.Kind.MONEY_REQUEST_RESULT)


def user_notifications(user, *, limit: int = 12):
    return notifications_for_session_user(user).select_related(
        "actor",
        "money_request",
        "money_request__requester",
    )[:limit]


def unread_notification_count(user) -> int:
    return notifications_for_session_user(user).filter(is_read=False).count()

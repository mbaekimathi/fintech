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
    return User.objects.filter(
        is_active=True,
        is_approved=True,
        role__in=REVIEW_ROLES,
    ).exclude(role=User.Role.PENDING_APPROVAL)


def notify_money_request_submitted(money_request: MoneyRequest) -> int:
    requester = money_request.requester
    name = requester.get_full_name() or requester.staff_code
    dest = money_request.get_destination_type_display()
    title = f"{name} requested KES {money_request.amount:,.2f}"
    body = f"{dest} · {money_request.destination}"
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
    return Notification.objects.filter(
        money_request=money_request,
        kind=Notification.Kind.MONEY_REQUEST,
        is_read=False,
    ).update(is_read=True)


def mark_notification_read(notification: Notification) -> None:
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])


def user_notifications(user, *, limit: int = 12):
    return (
        Notification.objects.filter(recipient=user)
        .select_related("actor", "money_request", "money_request__requester")[:limit]
    )


def unread_notification_count(user) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).count()

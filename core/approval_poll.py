"""JSON payloads for live approval / pending-request polling."""

from __future__ import annotations

from django.urls import reverse

from core.models import Notification
from core.notifications import notifications_for_session_user
from paybill.models import MoneyRequest


def _pending_item(
    money_request: MoneyRequest,
    *,
    notification_id,
    title: str,
    body: str,
    is_unread: bool,
    review_url: str,
) -> dict:
    requester = money_request.requester
    name = requester.get_full_name() or requester.staff_code
    return {
        "notification_id": notification_id,
        "money_request_id": money_request.pk,
        "title": title,
        "body": body,
        "amount": str(money_request.amount),
        "is_unread": is_unread,
        "review_url": review_url,
        "created_at": money_request.created_at.isoformat(),
        "requester_name": name,
        "requester_code": requester.staff_code,
        "category": money_request.get_category_display(),
        "destination_type": money_request.get_destination_type_display(),
        "destination": money_request.destination,
        "account_ref": money_request.account_ref or "",
        "source_paybill": money_request.source_paybill.paybill_number,
        "amount_label": f"{money_request.amount:,.2f}",
    }


def pending_approval_queue_for_user(user) -> list[dict]:
    """Pending money requests for reviewers (notifications + any orphan pending row)."""
    pending: list[dict] = []
    seen_money_request_ids: set[int] = set()

    notes = (
        notifications_for_session_user(user)
        .filter(
            kind=Notification.Kind.MONEY_REQUEST,
            money_request__status=MoneyRequest.Status.PENDING,
        )
        .select_related(
            "money_request",
            "money_request__requester",
            "money_request__source_paybill",
        )
        .order_by("-created_at")[:15]
    )
    for note in notes:
        if not note.can_review:
            continue
        money_request = note.money_request
        seen_money_request_ids.add(money_request.pk)
        pending.append(
            _pending_item(
                money_request,
                notification_id=note.pk,
                title=note.title,
                body=note.body,
                is_unread=not note.is_read,
                review_url=reverse("core:notification-review", kwargs={"pk": note.pk}),
            )
        )

    extra = (
        MoneyRequest.objects.filter(status=MoneyRequest.Status.PENDING)
        .exclude(pk__in=seen_money_request_ids)
        .select_related("requester", "source_paybill")
        .order_by("-created_at")[:15]
    )
    for money_request in extra:
        if money_request.requester_id == user.pk:
            continue
        requester = money_request.requester
        name = requester.get_full_name() or requester.staff_code
        dest = money_request.get_destination_type_display()
        title = f"{name} requested KES {money_request.amount:,.2f}"
        body = f"{dest} · {money_request.destination}"
        if money_request.account_ref:
            body = f"{body} / {money_request.account_ref}"
        pending.append(
            _pending_item(
                money_request,
                notification_id=f"req-{money_request.pk}",
                title=title[:160],
                body=body[:255],
                is_unread=True,
                review_url=reverse(
                    "paybill:money-request-review",
                    kwargs={"pk": money_request.pk},
                ),
            )
        )

    return pending

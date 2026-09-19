"""Payment approval helpers."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.utils import timezone

from core.models import AppSettings
from integrations.callbacks import TERMINAL_STATUSES, apply_stk_query
from integrations.daraja import callback_urls
from integrations.daraja_client import DarajaClient, DarajaError
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import MoneyRequest

APPROVAL_STK_AMOUNT = Decimal("1")
APPROVAL_STK_REF_PREFIX = "APMR"
APPROVAL_STK_TTL = timedelta(minutes=10)


def app_approval_required() -> bool:
    return AppSettings.load().app_approval_required


def stk_pin_approval_required() -> bool:
    return AppSettings.load().stk_pin_approval_required


def verify_approval_pin(user, raw_pin: str) -> bool:
    pin = (raw_pin or "").strip()
    if not pin.isdigit() or len(pin) != 6:
        return False
    return user.check_approval_password(pin)


def user_requires_app_on_approval(user) -> bool:
    return user.requires_app_on_approval()


def user_requires_stk_on_approval(user) -> bool:
    return user.requires_stk_on_approval()


def approval_stk_account_ref(money_request_id: int) -> str:
    return f"{APPROVAL_STK_REF_PREFIX}{money_request_id}"[:12]


def is_approval_stk_operation(operation: DarajaOperation | None) -> bool:
    return bool(
        operation
        and operation.kind == DarajaOperation.Kind.STK
        and (operation.account_ref or "").startswith(APPROVAL_STK_REF_PREFIX)
    )


def _ack_fields(body: dict) -> dict:
    return {
        "merchant_request_id": body.get("MerchantRequestID") or "",
        "checkout_request_id": body.get("CheckoutRequestID") or "",
        "conversation_id": body.get("ConversationID") or "",
        "originator_conversation_id": body.get("OriginatorConversationID") or "",
        "result_desc": (body.get("ResponseDescription") or body.get("CustomerMessage") or "")[:255],
        "response_payload": body,
    }


def _redact(payload: dict) -> dict:
    data = dict(payload or {})
    for key in ("SecurityCredential", "Password"):
        if key in data:
            data[key] = "[redacted]"
    return data


def initiate_stk_approval(request, money_request: MoneyRequest) -> DarajaOperation:
    """Send an STK push to the approver's phone (same flow as Daraja test STK)."""
    phone = (request.user.phone or "").strip()
    if not phone:
        raise DarajaError("Add your phone number to your profile before PIN approval.")

    config = DarajaConfig.load()
    if not config.stk_ready:
        raise DarajaError("STK is not ready. Finish Daraja STK setup first.")

    client = DarajaClient(config)
    urls = callback_urls(request)
    callback_url = urls.get("stk_callback_url") or ""
    account_ref = approval_stk_account_ref(money_request.pk)
    body, payload = client.stk_push(
        phone=phone,
        amount=APPROVAL_STK_AMOUNT,
        account_ref=account_ref,
        callback_url=callback_url,
    )
    return DarajaOperation.objects.create(
        kind=DarajaOperation.Kind.STK,
        destination=payload["PhoneNumber"],
        amount=APPROVAL_STK_AMOUNT,
        account_ref=account_ref,
        request_payload=_redact(payload),
        summary=body.get("CustomerMessage") or "Check your phone for the M-Pesa PIN prompt.",
        created_by=request.user,
        **_ack_fields(body),
    )


def poll_stk_approval(operation: DarajaOperation) -> DarajaOperation:
    """Query Safaricom for STK status when still queued (same as Daraja test refresh)."""
    if (
        operation.status == DarajaOperation.Status.QUEUED
        and operation.checkout_request_id
        and is_approval_stk_operation(operation)
    ):
        body = DarajaClient(DarajaConfig.load()).stk_query(operation.checkout_request_id)
        apply_stk_query(operation, body)
    return operation


def verify_stk_approval(user, operation_id, money_request: MoneyRequest) -> bool:
    operation = DarajaOperation.objects.filter(
        pk=operation_id,
        kind=DarajaOperation.Kind.STK,
        created_by=user,
    ).first()
    if not is_approval_stk_operation(operation):
        return False
    if operation.account_ref != approval_stk_account_ref(money_request.pk):
        return False
    if operation.status != DarajaOperation.Status.SUCCESS:
        return False
    created = operation.created_at
    if timezone.is_naive(created):
        created = timezone.make_aware(created, timezone.get_current_timezone())
    return timezone.now() - created <= APPROVAL_STK_TTL


def approval_pin_ok(request, *, next_url: str) -> bool:
    """Return True when in-app approval may proceed (PIN verified or not required)."""
    if not user_requires_app_on_approval(request.user):
        return True
    user = request.user
    if not user.has_approval_password:
        messages.error(
            request,
            "Set your approval password on Profile before approving payments.",
        )
        return False
    if verify_approval_pin(user, request.POST.get("approval_pin", "")):
        return True
    messages.error(request, "Enter your 6-digit approval password to approve this payment.")
    return False


def stk_approval_ok(request, *, money_request: MoneyRequest, next_url: str) -> bool:
    """Return True when STK PIN approval succeeded or is not required."""
    if not user_requires_stk_on_approval(request.user):
        return True
    raw_id = (request.POST.get("stk_approval_operation_id") or "").strip()
    if raw_id.isdigit() and verify_stk_approval(request.user, int(raw_id), money_request):
        return True
    messages.error(request, "Complete the M-Pesa PIN prompt on your phone to approve this payment.")
    return False


def approval_ok(request, *, money_request: MoneyRequest, next_url: str) -> bool:
    """Return True when all enabled approval checks pass."""
    if not approval_pin_ok(request, next_url=next_url):
        return False
    return stk_approval_ok(request, money_request=money_request, next_url=next_url)

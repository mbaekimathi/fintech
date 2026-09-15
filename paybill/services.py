"""Money request approval and Daraja payout helpers."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from accounts.utils import write_audit
from integrations.callbacks import wait_for_result
from integrations.daraja import callback_urls
from integrations.daraja_client import DarajaClient, DarajaError
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import MoneyRequest

MPESA_RECEIPT_KEYS = (
    "TransactionReceipt",
    "ReceiptNo",
    "MpesaReceiptNumber",
    "TransactionID",
    "TransID",
)


def extract_mpesa_receipt(
    *,
    receipt: str = "",
    items: dict | None = None,
    payload: dict | None = None,
    summary: str = "",
) -> str:
    """Normalize an M-Pesa receipt from any common Daraja callback shape."""
    candidate = str(receipt or "").strip()
    if candidate:
        return candidate[:64]

    values = dict(items or {})
    if payload:
        result = payload.get("Result") or payload
        params = ((result.get("ResultParameters") or {}).get("ResultParameter")) or []
        if isinstance(params, dict):
            params = [params]
        for row in params:
            if isinstance(row, dict) and row.get("Key"):
                values.setdefault(row.get("Key"), row.get("Value"))
        # STK callback metadata uses Name/Value instead of Key/Value.
        callback = ((payload.get("Body") or {}).get("stkCallback")) or {}
        meta = ((callback.get("CallbackMetadata") or {}).get("Item")) or []
        if isinstance(meta, dict):
            meta = [meta]
        for row in meta:
            if isinstance(row, dict) and row.get("Name"):
                values.setdefault(row.get("Name"), row.get("Value"))

    for key in MPESA_RECEIPT_KEYS:
        value = str(values.get(key) or "").strip()
        if value:
            return value[:64]

    text = (summary or "").strip()
    if " · " in text:
        tail = text.rsplit(" · ", 1)[-1].strip()
        if tail and "KES" not in tail.upper() and " " not in tail:
            return tail[:64]
    return ""


def mpesa_receipt_from_operation(operation) -> str:
    """Return the M-Pesa transaction receipt / reference from a Daraja result."""
    if operation is None:
        return ""
    stored = str(getattr(operation, "mpesa_reference", "") or "").strip()
    if stored:
        return stored[:64]
    return extract_mpesa_receipt(
        payload=operation.result_payload,
        summary=operation.summary,
    )


def money_request_ledger_reference(money_request: MoneyRequest, operation: DarajaOperation) -> str:
    return f"MR-{money_request.pk}-OP-{operation.pk}"[:64]


def money_request_meta(money_request: MoneyRequest, *, mpesa_reference: str = "") -> dict:
    requester = money_request.requester
    initiator = (requester.get_full_name() or requester.staff_code or "")[:160]
    return {
        "id": money_request.pk,
        "category": money_request.category,
        "category_label": money_request.get_category_display(),
        "reason": money_request.reason,
        "initiator": initiator,
        "initiator_code": requester.staff_code,
        "mpesa_reference": mpesa_reference,
        "destination_type": money_request.destination_type,
        "destination": money_request.destination,
        "account_ref": money_request.account_ref,
    }


def ensure_money_request_ledger_entry(
    money_request: MoneyRequest, operation: DarajaOperation
) -> "LedgerEntry":
    """Create or refresh the outbound ledger row so initiator/category show immediately."""
    from paybill.models import LedgerEntry

    account = money_request.source_paybill
    reference = money_request_ledger_reference(money_request, operation)
    initiator = (money_request.requester.get_full_name() or money_request.requester.staff_code or "")[
        :160
    ]
    category = money_request.get_category_display()
    reason = money_request.reason
    narrative = f"{category}: {reason}"[:255]
    raw_payload = {"_money_request": money_request_meta(money_request)}

    entry = (
        LedgerEntry.objects.filter(money_request=money_request)
        .exclude(status=LedgerEntry.Status.REVERSED)
        .order_by("-posted_at")
        .first()
    )
    if entry is None:
        entry = LedgerEntry.objects.filter(reference=reference).first()
    if entry is None:
        return LedgerEntry.objects.create(
            reference=reference,
            money_request=money_request,
            expense_category=category,
            expense_reason=reason,
            paybill_account=account,
            connected_system=account.connected_system,
            direction=LedgerEntry.Direction.OUT,
            amount=money_request.amount,
            payer_name=initiator,
            payer_phone=money_request.destination[:20],
            account_ref=money_request.account_ref,
            status=LedgerEntry.Status.PENDING,
            narrative=narrative,
            raw_payload=raw_payload,
        )

    entry.money_request = money_request
    entry.expense_category = category
    entry.expense_reason = reason
    entry.payer_name = initiator or entry.payer_name
    entry.narrative = narrative
    entry.raw_payload = {**(entry.raw_payload or {}), **raw_payload}
    if entry.status == LedgerEntry.Status.FAILED:
        entry.status = LedgerEntry.Status.PENDING
        entry.reference = reference
        entry.mpesa_reference = ""
    entry.save()
    return entry


def clear_pending_money_request_ledger(money_request: MoneyRequest) -> int:
    from paybill.models import LedgerEntry

    return LedgerEntry.objects.filter(
        money_request=money_request,
        status=LedgerEntry.Status.PENDING,
    ).update(status=LedgerEntry.Status.FAILED)


def money_request_by_ledger_reference() -> dict[str, MoneyRequest]:
    """Map ledger entry references to the money request that initiated the payout."""
    mapping: dict[str, MoneyRequest] = {}
    qs = MoneyRequest.objects.select_related(
        "requester", "daraja_operation", "source_paybill"
    )
    for money_request in qs:
        mapping[f"MR-{money_request.pk}"] = money_request
        if money_request.mpesa_reference:
            mapping[money_request.mpesa_reference[:64]] = money_request
        operation = money_request.daraja_operation
        if operation is None:
            continue
        mapping[money_request_ledger_reference(money_request, operation)] = money_request
        mapping[f"{operation.kind}-{operation.pk}"] = money_request
        receipt = (
            str(money_request.mpesa_reference or "").strip()
            or mpesa_receipt_from_operation(operation)
        )
        if receipt:
            mapping[receipt[:64]] = money_request
    return mapping


def _redact(payload: dict) -> dict:
    data = dict(payload or {})
    for key in ("SecurityCredential", "Password"):
        if key in data:
            data[key] = "[redacted]"
    return data


def _ack_fields(body: dict) -> dict:
    return {
        "merchant_request_id": body.get("MerchantRequestID") or "",
        "checkout_request_id": body.get("CheckoutRequestID") or "",
        "conversation_id": body.get("ConversationID") or "",
        "originator_conversation_id": body.get("OriginatorConversationID") or "",
        "result_desc": (body.get("ResponseDescription") or body.get("CustomerMessage") or "")[:255],
        "response_payload": body,
    }


def reject_money_request(request, money_request: MoneyRequest) -> MoneyRequest:
    if money_request.status != MoneyRequest.Status.PENDING:
        raise ValueError("Only pending requests can be rejected.")
    money_request.status = MoneyRequest.Status.REJECTED
    money_request.reviewed_by = request.user
    money_request.reviewed_at = timezone.now()
    money_request.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"]
    )
    write_audit(
        request,
        "money_request.reject",
        object_type="money_request",
        object_id=money_request.pk,
        detail={"amount": str(money_request.amount), "destination": money_request.destination},
    )
    return money_request


def approve_and_transfer(request, money_request: MoneyRequest) -> tuple[MoneyRequest, DarajaOperation]:
    """Approve a pending request and queue the Daraja payout."""
    if money_request.status != MoneyRequest.Status.PENDING:
        raise ValueError("Only pending requests can be approved.")

    config = DarajaConfig.load()
    client = DarajaClient(config)
    urls = callback_urls(request)
    result_url = urls.get("result_url") or ""
    timeout_url = urls.get("timeout_url") or ""
    dest_type = money_request.destination_type

    if dest_type == MoneyRequest.DestinationType.PHONE:
        if not config.b2c_ready:
            raise DarajaError("Phone payout is not ready. Turn on B2C on Daraja setup.")
        body, payload, dest = client.b2c_send(
            phone=money_request.destination,
            amount=money_request.amount,
            result_url=result_url,
            timeout_url=timeout_url,
        )
        kind = DarajaOperation.Kind.B2C
        account_ref = money_request.account_ref or ""
    else:
        if not config.b2b_ready:
            raise DarajaError("Paybill/till payout is not ready. Turn on B2B on Daraja setup.")
        body, payload, dest = client.b2b_send(
            destination=money_request.destination,
            amount=money_request.amount,
            to_till=dest_type == MoneyRequest.DestinationType.TILL,
            account_ref=money_request.account_ref or "",
            result_url=result_url,
            timeout_url=timeout_url,
        )
        kind = DarajaOperation.Kind.B2B
        account_ref = money_request.account_ref or ""

    with transaction.atomic():
        operation = DarajaOperation.objects.create(
            kind=kind,
            destination=dest,
            amount=money_request.amount,
            account_ref=account_ref,
            request_payload=_redact(payload),
            summary=body.get("ResponseDescription") or "Payout queued.",
            created_by=request.user,
            **_ack_fields(body),
        )
        money_request.status = MoneyRequest.Status.APPROVED
        money_request.reviewed_by = request.user
        money_request.reviewed_at = timezone.now()
        money_request.daraja_operation = operation
        money_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "daraja_operation",
                "updated_at",
            ]
        )
        ensure_money_request_ledger_entry(money_request, operation)

    operation = wait_for_result(operation)
    money_request.refresh_from_db()
    sync_money_request_from_operation(operation)
    money_request.refresh_from_db()
    if operation.status == DarajaOperation.Status.SUCCESS:
        if money_request.status != MoneyRequest.Status.PAID:
            money_request.status = MoneyRequest.Status.PAID
            money_request.save(update_fields=["status", "updated_at"])
        receipt = mpesa_receipt_from_operation(operation)
        if receipt and money_request.mpesa_reference != receipt:
            money_request.mpesa_reference = receipt
            money_request.save(update_fields=["mpesa_reference", "updated_at"])
        # Callback normally posts the ledger; retry here if the row is still open.
        if receipt:
            from integrations.callbacks import _post_ledger

            _post_ledger(
                operation,
                amount=money_request.amount,
                phone=operation.destination or money_request.destination,
                receipt=receipt,
                inbound=False,
            )
    elif operation.status in {
        DarajaOperation.Status.FAILED,
        DarajaOperation.Status.TIMEOUT,
    }:
        # Keep APPROVED so staff can see it left pending queue, or reopen for retry.
        # Revert to PENDING so Approve can be tried again after fixing Daraja.
        clear_pending_money_request_ledger(money_request)
        money_request.status = MoneyRequest.Status.PENDING
        money_request.daraja_operation = None
        money_request.save(update_fields=["status", "daraja_operation", "updated_at"])

    write_audit(
        request,
        "money_request.approve",
        object_type="money_request",
        object_id=money_request.pk,
        detail={
            "amount": str(money_request.amount),
            "destination": dest,
            "operation_id": operation.pk,
            "operation_status": operation.status,
            "request_status": money_request.status,
        },
    )
    return money_request, operation


def sync_money_request_from_operation(operation: DarajaOperation) -> MoneyRequest | None:
    """Update linked money request when a Daraja result arrives."""
    money_request = getattr(operation, "money_request", None)
    if money_request is None:
        try:
            money_request = MoneyRequest.objects.get(daraja_operation=operation)
        except MoneyRequest.DoesNotExist:
            return None

    receipt = mpesa_receipt_from_operation(operation)
    if receipt and operation.mpesa_reference != receipt:
        operation.mpesa_reference = receipt
        operation.save(update_fields=["mpesa_reference", "updated_at"])

    if operation.status == DarajaOperation.Status.SUCCESS:
        update_fields = ["updated_at"]
        if money_request.status != MoneyRequest.Status.PAID:
            money_request.status = MoneyRequest.Status.PAID
            update_fields.append("status")
        if receipt and money_request.mpesa_reference != receipt:
            money_request.mpesa_reference = receipt
            update_fields.append("mpesa_reference")
        if len(update_fields) > 1:
            money_request.save(update_fields=update_fields)
    elif operation.status in {
        DarajaOperation.Status.FAILED,
        DarajaOperation.Status.TIMEOUT,
    }:
        if money_request.status in {
            MoneyRequest.Status.APPROVED,
            MoneyRequest.Status.PENDING,
        }:
            clear_pending_money_request_ledger(money_request)
            money_request.status = MoneyRequest.Status.PENDING
            money_request.daraja_operation = None
            money_request.save(update_fields=["status", "daraja_operation", "updated_at"])
    return money_request

"""Persist Daraja callback and STK query results."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from time import monotonic, sleep

from django.utils import timezone

from integrations.models import DarajaOperation
from paybill.models import LedgerEntry, PaybillAccount


TERMINAL_STATUSES = {
    DarajaOperation.Status.SUCCESS,
    DarajaOperation.Status.FAILED,
    DarajaOperation.Status.TIMEOUT,
}


def format_account_balances(raw: str) -> str:
    parts = []
    for chunk in (raw or "").split("&"):
        bits = [bit.strip() for bit in chunk.split("|") if bit.strip()]
        if len(bits) >= 3:
            name = bits[0].replace(" Account", "").strip()
            parts.append(f"{name} {bits[1]} {bits[2]}")
    return " · ".join(parts) if parts else (raw or "").strip()


def wait_for_result(operation: DarajaOperation, timeout: float = 8.0, interval: float = 0.3) -> DarajaOperation:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        operation.refresh_from_db()
        if operation.status in TERMINAL_STATUSES:
            return operation
        sleep(interval)
    operation.refresh_from_db()
    return operation


NO_RESULT_SUMMARY = (
    "No result callback. Party A 600996 is saved. Enable Account Balance and B2C on the Daraja app, keep one ngrok URL, retry."
)


def expire_stale_queues(seconds: int = 75) -> int:
    cutoff = timezone.now() - timedelta(seconds=seconds)
    rows = DarajaOperation.objects.filter(
        status=DarajaOperation.Status.QUEUED,
        created_at__lt=cutoff,
    ).exclude(kind=DarajaOperation.Kind.STK)
    count = 0
    for operation in rows:
        operation.status = DarajaOperation.Status.TIMEOUT
        operation.summary = NO_RESULT_SUMMARY
        operation.result_desc = "No ResultURL callback from Safaricom."
        operation.save(update_fields=["status", "summary", "result_desc", "updated_at"])
        count += 1
    return count


def _items(payload: dict) -> dict:
    result = payload.get("Result") or {}
    params = ((result.get("ResultParameters") or {}).get("ResultParameter")) or []
    if isinstance(params, dict):
        params = [params]
    return {row.get("Key"): row.get("Value") for row in params if isinstance(row, dict)}


def _stk_items(payload: dict) -> dict:
    callback = ((payload.get("Body") or {}).get("stkCallback")) or {}
    meta = ((callback.get("CallbackMetadata") or {}).get("Item")) or []
    if isinstance(meta, dict):
        meta = [meta]
    return {row.get("Name"): row.get("Value") for row in meta if isinstance(row, dict)}, callback


def apply_stk_query(operation: DarajaOperation, payload: dict) -> DarajaOperation:
    code = str(payload.get("ResultCode", ""))
    operation.result_payload = payload
    operation.result_code = code
    operation.result_desc = (payload.get("ResultDesc") or "")[:255]
    if code in {"0", "00"}:
        operation.status = DarajaOperation.Status.SUCCESS
        operation.summary = operation.result_desc or "Payment completed."
    else:
        operation.status = DarajaOperation.Status.FAILED
        operation.summary = operation.result_desc or "STK was not completed."
    operation.save()
    return operation


def apply_stk_callback(payload: dict) -> DarajaOperation | None:
    items, callback = _stk_items(payload)
    checkout = callback.get("CheckoutRequestID") or ""
    operation = None
    if checkout:
        operation = DarajaOperation.objects.filter(checkout_request_id=checkout).first()
    if operation is None:
        merchant = callback.get("MerchantRequestID") or ""
        if merchant:
            operation = DarajaOperation.objects.filter(merchant_request_id=merchant).first()
    if operation is None:
        return None
    code = str(callback.get("ResultCode", ""))
    operation.result_payload = payload
    operation.result_code = code
    operation.result_desc = (callback.get("ResultDesc") or "")[:255]
    receipt = str(items.get("MpesaReceiptNumber") or "")
    amount = items.get("Amount")
    phone = str(items.get("PhoneNumber") or operation.destination)
    if code in {"0", "00"}:
        operation.status = DarajaOperation.Status.SUCCESS
        operation.summary = f"Paid KES {amount} · {receipt}".strip(" ·")
        _post_ledger(operation, amount=amount, phone=phone, receipt=receipt, inbound=True)
    else:
        operation.status = DarajaOperation.Status.FAILED
        operation.summary = operation.result_desc or "Customer did not complete STK."
    operation.save()
    return operation


def apply_result_callback(payload: dict) -> DarajaOperation | None:
    result = payload.get("Result") or payload
    origin = result.get("OriginatorConversationID") or ""
    conversation = result.get("ConversationID") or ""
    operation = None
    if origin:
        operation = DarajaOperation.objects.filter(originator_conversation_id=origin).first()
    if operation is None and conversation:
        operation = DarajaOperation.objects.filter(conversation_id=conversation).first()
    if operation is None:
        return None
    code = str(result.get("ResultCode", ""))
    items = _items(payload)
    operation.result_payload = payload
    operation.result_code = code
    operation.result_desc = (result.get("ResultDesc") or "")[:255]
    if operation.kind == DarajaOperation.Kind.BALANCE:
        balances = str(
            items.get("AccountBalance")
            or items.get("BOCompletedTime")
            or ""
        )
        operation.summary = format_account_balances(balances) or operation.result_desc
        operation.status = DarajaOperation.Status.SUCCESS if code in {"0", "00"} else DarajaOperation.Status.FAILED
    elif code in {"0", "00"}:
        operation.status = DarajaOperation.Status.SUCCESS
        receipt = str(items.get("TransactionReceipt") or items.get("ReceiptNo") or "")
        amount = items.get("TransactionAmount") or items.get("Amount") or operation.amount
        operation.summary = f"Sent KES {amount} · {receipt}".strip(" ·")
        phone = str(items.get("ReceiverPartyPublicName") or operation.destination)
        _post_ledger(operation, amount=amount, phone=phone, receipt=receipt, inbound=False)
    else:
        operation.status = DarajaOperation.Status.FAILED
        operation.summary = operation.result_desc or "Daraja result failed."
    if str(result.get("ResultType")) == "timeout" or "timed out" in operation.result_desc.lower():
        operation.status = DarajaOperation.Status.TIMEOUT
    operation.save()
    return operation


def apply_timeout_callback(payload: dict) -> DarajaOperation | None:
    result = payload.get("Result") or payload
    origin = result.get("OriginatorConversationID") or ""
    operation = DarajaOperation.objects.filter(originator_conversation_id=origin).first() if origin else None
    if operation is None:
        conversation = result.get("ConversationID") or ""
        if conversation:
            operation = DarajaOperation.objects.filter(conversation_id=conversation).first()
    if operation is None:
        return None
    operation.result_payload = payload
    operation.status = DarajaOperation.Status.TIMEOUT
    operation.result_desc = (result.get("ResultDesc") or "Request timed out.")[:255]
    operation.summary = operation.result_desc
    operation.save()
    return operation


def _post_ledger(operation: DarajaOperation, *, amount, phone: str, receipt: str, inbound: bool):
    from integrations.models import DarajaConfig

    config = DarajaConfig.load()
    account = config.paybill_account
    if account is None:
        account = PaybillAccount.objects.filter(paybill_number=config.shortcode).first()
    if account is None:
        return
    try:
        money = Decimal(str(amount if amount is not None else operation.amount or 0))
    except (InvalidOperation, TypeError):
        return
    reference = (receipt or f"{operation.kind}-{operation.pk}")[:64]
    if LedgerEntry.objects.filter(reference=reference).exists():
        return
    LedgerEntry.objects.create(
        reference=reference,
        paybill_account=account,
        connected_system=account.connected_system,
        direction=LedgerEntry.Direction.IN if inbound else LedgerEntry.Direction.OUT,
        amount=money,
        payer_phone=str(phone)[:20],
        account_ref=operation.account_ref,
        status=LedgerEntry.Status.COMPLETED,
        narrative=operation.get_kind_display(),
        raw_payload=operation.result_payload or operation.response_payload,
    )

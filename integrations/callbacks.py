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


def parse_account_balances(raw: str) -> dict:
    """Parse Safaricom AccountBalance payload into named float buckets."""
    accounts = {}
    for chunk in (raw or "").split("&"):
        bits = [bit.strip() for bit in chunk.split("|") if bit.strip()]
        if len(bits) < 3:
            continue
        label = bits[0].replace(" Account", "").strip()
        key = label.lower()
        try:
            amount = Decimal(str(bits[2]).replace(",", ""))
        except (InvalidOperation, ValueError):
            amount = None
        accounts[key] = {"label": label, "currency": bits[1], "amount": amount}
    return accounts


def parse_balance_summary(summary: str) -> dict:
    """Parse formatted balance text such as ``Working KES 100.00 · Utility KES 12.50``."""
    accounts = {}
    for part in (summary or "").split("·"):
        tokens = part.strip().split()
        if len(tokens) < 3:
            continue
        label = tokens[0]
        key = label.lower()
        try:
            amount = Decimal(tokens[-1].replace(",", ""))
        except (InvalidOperation, ValueError):
            amount = None
        accounts[key] = {
            "label": label,
            "currency": tokens[1] if len(tokens) > 2 else "KES",
            "amount": amount,
        }
    return accounts


def balance_accounts_from_operation(operation) -> dict:
    if operation is None:
        return {}
    summary = (operation.summary or operation.result_desc or "").strip()
    if "|" in summary or "&" in summary:
        return parse_account_balances(summary)
    return parse_balance_summary(summary)


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
    from paybill.services import sync_money_request_from_operation

    for operation in rows:
        operation.status = DarajaOperation.Status.TIMEOUT
        operation.summary = NO_RESULT_SUMMARY
        operation.result_desc = "No ResultURL callback from Safaricom."
        operation.save(update_fields=["status", "summary", "result_desc", "updated_at"])
        sync_money_request_from_operation(operation)
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
    receipt = str(items.get("MpesaReceiptNumber") or items.get("TransactionReceipt") or "")
    amount = items.get("Amount")
    phone = str(items.get("PhoneNumber") or operation.destination)
    if code in {"0", "00"}:
        operation.status = DarajaOperation.Status.SUCCESS
        receipt = operation.capture_mpesa_reference(receipt, items=items)
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
        receipt = operation.capture_mpesa_reference(
            str(items.get("TransactionReceipt") or items.get("ReceiptNo") or items.get("TransactionID") or ""),
            items=items,
        )
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
    from paybill.services import sync_money_request_from_operation

    sync_money_request_from_operation(operation)
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
    from paybill.services import sync_money_request_from_operation

    sync_money_request_from_operation(operation)
    return operation


def _post_ledger(operation: DarajaOperation, *, amount, phone: str, receipt: str, inbound: bool):
    from integrations.models import DarajaConfig
    from paybill.models import LedgerEntry, MoneyRequest
    from paybill.services import extract_mpesa_receipt, money_request_meta

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

    mpesa_reference = extract_mpesa_receipt(
        receipt=receipt or operation.mpesa_reference,
        payload=operation.result_payload,
        summary=operation.summary,
    )
    if mpesa_reference and operation.mpesa_reference != mpesa_reference:
        operation.mpesa_reference = mpesa_reference
        operation.save(update_fields=["mpesa_reference", "updated_at"])

    reference = (mpesa_reference or f"{operation.kind}-{operation.pk}")[:64]

    money_request = getattr(operation, "money_request", None)
    if money_request is None:
        money_request = (
            MoneyRequest.objects.filter(daraja_operation=operation)
            .select_related("requester")
            .first()
        )

    existing = LedgerEntry.objects.filter(reference=reference).first()
    if existing is None and money_request is not None:
        existing = (
            LedgerEntry.objects.filter(money_request=money_request)
            .exclude(status=LedgerEntry.Status.REVERSED)
            .order_by("-posted_at")
            .first()
        )

    payer_name = ""
    expense_category = ""
    expense_reason = ""
    narrative = operation.get_kind_display()
    raw_payload = dict(operation.result_payload or operation.response_payload or {})
    if money_request is not None:
        requester = money_request.requester
        payer_name = (requester.get_full_name() or requester.staff_code or "")[:160]
        expense_category = money_request.get_category_display()
        expense_reason = money_request.reason
        narrative = f"{expense_category}: {expense_reason}"[:255]
        raw_payload["_money_request"] = money_request_meta(
            money_request, mpesa_reference=mpesa_reference
        )
        if mpesa_reference and money_request.mpesa_reference != mpesa_reference:
            money_request.mpesa_reference = mpesa_reference
            money_request.save(update_fields=["mpesa_reference", "updated_at"])

    if existing is not None:
        updates = {
            "mpesa_reference": mpesa_reference or existing.mpesa_reference,
            "amount": money,
            "payer_phone": str(phone)[:20] or existing.payer_phone,
            "account_ref": operation.account_ref or existing.account_ref,
            "status": LedgerEntry.Status.COMPLETED,
            "narrative": narrative or existing.narrative,
            "raw_payload": raw_payload or existing.raw_payload,
            "direction": LedgerEntry.Direction.IN if inbound else LedgerEntry.Direction.OUT,
        }
        if payer_name:
            updates["payer_name"] = payer_name
        if expense_category:
            updates["expense_category"] = expense_category
        if expense_reason:
            updates["expense_reason"] = expense_reason
        if money_request is not None:
            updates["money_request"] = money_request
        if existing.reference != reference and not LedgerEntry.objects.filter(reference=reference).exclude(pk=existing.pk).exists():
            updates["reference"] = reference
        for field, value in updates.items():
            setattr(existing, field, value)
        existing.save(update_fields=[*updates.keys()])
        return

    LedgerEntry.objects.create(
        reference=reference,
        mpesa_reference=mpesa_reference,
        money_request=money_request,
        expense_category=expense_category,
        expense_reason=expense_reason,
        paybill_account=account,
        connected_system=account.connected_system,
        direction=LedgerEntry.Direction.IN if inbound else LedgerEntry.Direction.OUT,
        amount=money,
        payer_name=payer_name,
        payer_phone=str(phone)[:20],
        account_ref=operation.account_ref,
        status=LedgerEntry.Status.COMPLETED,
        narrative=narrative,
        raw_payload=raw_payload,
    )

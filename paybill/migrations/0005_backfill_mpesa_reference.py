# Backfill stored M-Pesa references from existing Daraja payloads and ledger refs.

from django.db import migrations

RECEIPT_KEYS = (
    "TransactionReceipt",
    "ReceiptNo",
    "MpesaReceiptNumber",
    "TransactionID",
    "TransID",
)


def _extract(payload=None, summary="", receipt=""):
    candidate = str(receipt or "").strip()
    if candidate:
        return candidate[:64]
    values = {}
    payload = payload or {}
    result = payload.get("Result") or payload
    params = ((result.get("ResultParameters") or {}).get("ResultParameter")) or []
    if isinstance(params, dict):
        params = [params]
    for row in params:
        if isinstance(row, dict) and row.get("Key"):
            values.setdefault(row.get("Key"), row.get("Value"))
    callback = ((payload.get("Body") or {}).get("stkCallback")) or {}
    meta = ((callback.get("CallbackMetadata") or {}).get("Item")) or []
    if isinstance(meta, dict):
        meta = [meta]
    for row in meta:
        if isinstance(row, dict) and row.get("Name"):
            values.setdefault(row.get("Name"), row.get("Value"))
    for key in RECEIPT_KEYS:
        value = str(values.get(key) or "").strip()
        if value:
            return value[:64]
    text = (summary or "").strip()
    if " · " in text:
        tail = text.rsplit(" · ", 1)[-1].strip()
        if tail and "KES" not in tail.upper() and " " not in tail:
            return tail[:64]
    return ""


def backfill(apps, schema_editor):
    DarajaOperation = apps.get_model("integrations", "DarajaOperation")
    MoneyRequest = apps.get_model("paybill", "MoneyRequest")
    LedgerEntry = apps.get_model("paybill", "LedgerEntry")

    for operation in DarajaOperation.objects.all().iterator():
        if operation.mpesa_reference:
            continue
        receipt = _extract(operation.result_payload, operation.summary)
        if receipt:
            operation.mpesa_reference = receipt
            operation.save(update_fields=["mpesa_reference"])

    for money_request in MoneyRequest.objects.select_related("daraja_operation").iterator():
        if money_request.mpesa_reference:
            continue
        operation = money_request.daraja_operation
        receipt = ""
        if operation is not None:
            receipt = (operation.mpesa_reference or "").strip() or _extract(
                operation.result_payload, operation.summary
            )
        if receipt:
            money_request.mpesa_reference = receipt
            money_request.save(update_fields=["mpesa_reference"])

    for entry in LedgerEntry.objects.all().iterator():
        if entry.mpesa_reference:
            continue
        receipt = ""
        payload = entry.raw_payload or {}
        meta = payload.get("_money_request") or {}
        receipt = str(meta.get("mpesa_reference") or "").strip()
        if not receipt:
            receipt = _extract(payload)
        if not receipt:
            reference = (entry.reference or "").strip()
            # Skip synthetic fallbacks like B2C-12 / B2B-3.
            if reference and not (
                reference.count("-") == 1
                and reference.split("-", 1)[0] in {"STK", "BALANCE", "B2C", "B2B"}
                and reference.split("-", 1)[1].isdigit()
            ):
                receipt = reference[:64]
        if receipt:
            entry.mpesa_reference = receipt
            entry.save(update_fields=["mpesa_reference"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("paybill", "0004_mpesa_reference"),
        ("integrations", "0009_mpesa_reference"),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]

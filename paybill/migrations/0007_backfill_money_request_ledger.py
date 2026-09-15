from django.db import migrations


def backfill_money_request_ledger(apps, schema_editor):
    MoneyRequest = apps.get_model("paybill", "MoneyRequest")
    LedgerEntry = apps.get_model("paybill", "LedgerEntry")

    for money_request in (
        MoneyRequest.objects.filter(status__in=["APPROVED", "PAID"])
        .select_related("requester", "source_paybill", "daraja_operation")
        .iterator()
    ):
        existing = (
            LedgerEntry.objects.filter(money_request_id=money_request.pk)
            .exclude(status="REVERSED")
            .first()
        )
        if existing is not None:
            continue

        operation = money_request.daraja_operation
        if operation is not None:
            reference = f"MR-{money_request.pk}-OP-{operation.pk}"[:64]
        elif money_request.mpesa_reference:
            reference = money_request.mpesa_reference[:64]
        else:
            reference = f"MR-{money_request.pk}"[:64]

        if LedgerEntry.objects.filter(reference=reference).exists():
            entry = LedgerEntry.objects.get(reference=reference)
            entry.money_request_id = money_request.pk
            requester = money_request.requester
            initiator = (
                f"{requester.first_name} {requester.last_name}".strip()
                or requester.staff_code
                or ""
            )[:160]
            category = dict(MoneyRequest._meta.get_field("category").choices).get(
                money_request.category, money_request.category
            )
            entry.payer_name = entry.payer_name or initiator
            entry.expense_category = entry.expense_category or category
            entry.expense_reason = entry.expense_reason or money_request.reason
            payload = dict(entry.raw_payload or {})
            payload["_money_request"] = {
                "id": money_request.pk,
                "category": money_request.category,
                "category_label": category,
                "reason": money_request.reason,
                "initiator": initiator,
                "initiator_code": requester.staff_code,
                "mpesa_reference": money_request.mpesa_reference or entry.mpesa_reference,
            }
            entry.raw_payload = payload
            entry.save()
            continue

        requester = money_request.requester
        initiator = (
            f"{requester.first_name} {requester.last_name}".strip()
            or requester.staff_code
            or ""
        )[:160]
        category = dict(MoneyRequest._meta.get_field("category").choices).get(
            money_request.category, money_request.category
        )
        account = money_request.source_paybill
        status = "COMPLETED" if money_request.status == "PAID" else "PENDING"
        LedgerEntry.objects.create(
            reference=reference,
            mpesa_reference=money_request.mpesa_reference or "",
            money_request_id=money_request.pk,
            expense_category=category,
            expense_reason=money_request.reason,
            paybill_account_id=account.pk,
            connected_system_id=account.connected_system_id,
            direction="OUT",
            amount=money_request.amount,
            payer_name=initiator,
            payer_phone=(money_request.destination or "")[:20],
            account_ref=money_request.account_ref or "",
            status=status,
            narrative=f"{category}: {money_request.reason}"[:255],
            raw_payload={
                "_money_request": {
                    "id": money_request.pk,
                    "category": money_request.category,
                    "category_label": category,
                    "reason": money_request.reason,
                    "initiator": initiator,
                    "initiator_code": requester.staff_code,
                    "mpesa_reference": money_request.mpesa_reference or "",
                }
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("paybill", "0006_ledger_money_request_category"),
    ]

    operations = [
        migrations.RunPython(backfill_money_request_ledger, noop),
    ]

"""One-off B2C payouts from a collection account page."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from integrations.daraja import callback_urls
from integrations.daraja_client import DarajaClient, DarajaError
from integrations.models import DarajaConfig, DarajaOperation
from paybill.auto_payout import normalize_client_phone
from paybill.models import CollectionMonitor
from paybill.services import _ack_fields, _redact


def execute_manual_monitor_transfer(
    monitor: CollectionMonitor,
    *,
    amount: Decimal,
    destination: str,
    request=None,
    created_by=None,
) -> DarajaOperation:
    if amount is None or amount < Decimal("1"):
        raise DarajaError("Amount must be at least KES 1.")

    config = DarajaConfig.load()
    if not config.b2c_ready:
        raise DarajaError("Phone payout needs B2C enabled on Daraja setup.")

    urls = callback_urls(request)
    result_url = urls.get("result_url") or (config.result_url or "").strip()
    timeout_url = urls.get("timeout_url") or (config.timeout_url or "").strip()
    if not result_url:
        raise DarajaError(
            "No public result URL configured. Set DARAJA_PUBLIC_BASE_URL on the server."
        )

    if not (destination or "").strip():
        raise DarajaError("Enter the phone number to pay.")

    phone = normalize_client_phone(destination)
    client = DarajaClient(config)
    body, payload, dest = client.b2c_send(
        phone=phone,
        amount=amount,
        result_url=result_url,
        timeout_url=timeout_url,
    )
    meta = {"manual_transfer": True, "monitor_id": monitor.pk}
    with transaction.atomic():
        return DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            destination=dest,
            amount=amount,
            account_ref=monitor.collection_code or "MANUAL",
            request_payload={**_redact(payload), **meta},
            summary=body.get("ResponseDescription") or "Manual B2C payout queued.",
            collection_monitor=monitor,
            created_by=created_by,
            **_ack_fields(body),
        )

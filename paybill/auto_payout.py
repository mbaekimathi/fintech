"""Queue B2C payouts to a client phone after collection inbound ledger posts."""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from integrations.daraja import callback_urls
from integrations.daraja_client import DarajaClient, DarajaError, kenya_msisdn
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import CollectionMonitor, LedgerEntry
from paybill.services import _ack_fields, _redact

logger = logging.getLogger(__name__)


def normalize_client_phone(raw: str) -> str:
    return kenya_msisdn((raw or "").strip())


def maybe_auto_payout_inbound(
    monitor: CollectionMonitor,
    entry: LedgerEntry,
) -> DarajaOperation | None:
    """Send collected amount to the configured client phone when automation is enabled."""
    if not monitor.auto_payout_enabled:
        return None
    if entry.direction != LedgerEntry.Direction.IN:
        return None
    if entry.status != LedgerEntry.Status.COMPLETED:
        return None
    if entry.amount is None or entry.amount < Decimal("1"):
        return None

    try:
        phone = normalize_client_phone(monitor.auto_payout_phone)
    except DarajaError:
        logger.warning(
            "Auto payout skipped for monitor %s: invalid client phone",
            monitor.collection_code,
        )
        return None

    if DarajaOperation.objects.filter(
        kind=DarajaOperation.Kind.B2C,
        request_payload__auto_payout_ledger_id=entry.pk,
    ).exists():
        return None

    config = DarajaConfig.load()
    if not config.b2c_ready:
        logger.warning(
            "Auto payout skipped for monitor %s: B2C not ready on Daraja setup",
            monitor.collection_code,
        )
        return None

    urls = callback_urls()
    result_url = urls.get("result_url") or ""
    timeout_url = urls.get("timeout_url") or ""
    if not result_url:
        logger.warning("Auto payout skipped: no public result URL configured")
        return None

    client = DarajaClient(config)
    try:
        body, payload, dest = client.b2c_send(
            phone=phone,
            amount=entry.amount,
            result_url=result_url,
            timeout_url=timeout_url,
        )
    except DarajaError as exc:
        logger.warning("Auto payout B2C failed for ledger %s: %s", entry.pk, exc)
        return None

    meta = {
        "auto_payout_ledger_id": entry.pk,
        "collection_monitor_id": monitor.pk,
        "collection_code": monitor.collection_code,
        "source_mpesa_reference": entry.mpesa_reference or entry.reference,
    }
    with transaction.atomic():
        operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            destination=dest,
            amount=entry.amount,
            account_ref=monitor.collection_code,
            request_payload={**_redact(payload), **meta},
            summary=body.get("ResponseDescription") or "Client auto payout queued.",
            collection_monitor=monitor,
            **_ack_fields(body),
        )
    return operation


def schedule_auto_payout_inbound(monitor: CollectionMonitor, entry: LedgerEntry) -> None:
    """Queue B2C after the inbound ledger row is committed (keeps Safaricom callbacks fast)."""
    if not monitor.auto_payout_enabled:
        return
    if entry.direction != LedgerEntry.Direction.IN:
        return
    if entry.status != LedgerEntry.Status.COMPLETED:
        return
    monitor_id = monitor.pk
    entry_id = entry.pk

    def _run() -> None:
        from paybill.models import CollectionMonitor as MonitorModel
        from paybill.models import LedgerEntry as EntryModel

        fresh_monitor = MonitorModel.objects.filter(pk=monitor_id, is_active=True).first()
        fresh_entry = EntryModel.objects.filter(pk=entry_id).first()
        if fresh_monitor and fresh_entry:
            maybe_auto_payout_inbound(fresh_monitor, fresh_entry)

    transaction.on_commit(_run)

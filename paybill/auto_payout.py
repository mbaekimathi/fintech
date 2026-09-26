"""Queue payouts after collection: optional utility→working, then B2C or B2B."""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from django.db import transaction

from integrations.daraja import callback_urls
from integrations.daraja_client import DarajaClient, DarajaError, kenya_msisdn
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import CollectionMonitor, LedgerEntry, MoneyRequest
from paybill.services import _ack_fields, _redact

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {
    DarajaOperation.Status.FAILED,
    DarajaOperation.Status.TIMEOUT,
}


def normalize_client_phone(raw: str) -> str:
    return kenya_msisdn((raw or "").strip())


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def monitor_payout_destination(monitor: CollectionMonitor) -> str:
    raw = (monitor.auto_payout_destination or monitor.auto_payout_phone or "").strip()
    return raw


def collection_credits_utility_float(monitor: CollectionMonitor) -> bool:
    """Paybill/till collections usually land in the utility bucket before payout."""
    return monitor.account_type in (
        CollectionMonitor.AccountType.PAYBILL,
        CollectionMonitor.AccountType.TILL,
    )


def payout_destination_requires_utility(monitor: CollectionMonitor) -> bool:
    """Paybill/till payouts need utility→working before B2B can send."""
    dest_type = monitor.auto_payout_destination_type or MoneyRequest.DestinationType.PHONE
    return dest_type in (
        MoneyRequest.DestinationType.PAYBILL,
        MoneyRequest.DestinationType.TILL,
    )


def should_move_utility_first(monitor: CollectionMonitor) -> bool:
    """
    Queue utility→working before the client payout when:
    - the account flag is on, or
    - sending to another paybill/till (always requires float move + B2B).
    Phone (B2C) on a paybill/till collection account respects the flag only.
    """
    if monitor.auto_payout_utility_first:
        return True
    return payout_destination_requires_utility(monitor)


def auto_payout_is_enabled(monitor: CollectionMonitor) -> bool:
    if not monitor.auto_payout_enabled:
        return False
    dest = monitor_payout_destination(monitor)
    if not dest:
        return False
    dest_type = monitor.auto_payout_destination_type or MoneyRequest.DestinationType.PHONE
    if dest_type == MoneyRequest.DestinationType.PAYBILL and not (
        monitor.auto_payout_account_ref or ""
    ).strip():
        return False
    return True


def _auto_payout_ops_for_ledger(ledger_entry_id: int):
    return DarajaOperation.objects.filter(
        request_payload__auto_payout_ledger_id=ledger_entry_id,
    )


def _chain_phase(operation: DarajaOperation) -> str:
    chain = (operation.request_payload or {}).get("auto_payout_chain") or {}
    return (chain.get("phase") or "payout").strip().lower()


def _payout_already_queued(ledger_entry_id: int) -> bool:
    """True when a final payout op exists and should not be duplicated."""
    for op in _auto_payout_ops_for_ledger(ledger_entry_id):
        if _chain_phase(op) == "utility":
            continue
        if op.status in _RETRYABLE_STATUSES:
            continue
        return True
    return False


def _utility_step_pending(ledger_entry_id: int) -> bool:
    """True while utility→working is queued and not yet finished."""
    for op in _auto_payout_ops_for_ledger(ledger_entry_id):
        if _chain_phase(op) != "utility":
            continue
        if op.status == DarajaOperation.Status.SUCCESS:
            return False
        if op.status in _RETRYABLE_STATUSES:
            continue
        return True
    return False


def _utility_step_succeeded(ledger_entry_id: int) -> bool:
    for op in _auto_payout_ops_for_ledger(ledger_entry_id):
        if _chain_phase(op) == "utility" and op.status == DarajaOperation.Status.SUCCESS:
            return True
    return False


def _chain_payload(*, monitor: CollectionMonitor, entry: LedgerEntry, phase: str) -> dict:
    return {
        "phase": phase,
        "monitor_id": monitor.pk,
        "ledger_entry_id": entry.pk,
        "collection_code": monitor.collection_code,
        "destination_type": monitor.auto_payout_destination_type,
    }


def execute_auto_payout_transfer(
    monitor: CollectionMonitor,
    entry: LedgerEntry,
    *,
    skip_utility: bool = False,
) -> DarajaOperation | None:
    """Send payout for one inbound ledger row (B2B/B2C, optional utility→working first)."""
    if entry.direction != LedgerEntry.Direction.IN or entry.status != LedgerEntry.Status.COMPLETED:
        return None
    if entry.amount is None or entry.amount < Decimal("1"):
        return None
    if not monitor.auto_payout_enabled:
        return None
    if _payout_already_queued(entry.pk):
        return None

    config = DarajaConfig.load()
    urls = callback_urls()
    result_url = urls.get("result_url") or (config.result_url or "").strip()
    timeout_url = urls.get("timeout_url") or (config.timeout_url or "").strip()
    if not result_url:
        logger.warning(
            "Auto payout skipped for ledger %s: no public result URL (set DARAJA_PUBLIC_BASE_URL)",
            entry.pk,
        )
        return None

    dest_type = monitor.auto_payout_destination_type or MoneyRequest.DestinationType.PHONE
    wants_utility = should_move_utility_first(monitor) and not skip_utility

    if wants_utility and _utility_step_succeeded(entry.pk):
        wants_utility = False
    elif wants_utility:
        if _utility_step_pending(entry.pk):
            return None
        if not config.b2b_ready:
            if dest_type == MoneyRequest.DestinationType.PHONE and config.b2c_ready:
                logger.info(
                    "Auto payout ledger %s: B2B not ready — sending B2C from working float (utility move off).",
                    entry.pk,
                )
                wants_utility = False
            else:
                logger.warning(
                    "Auto payout skipped for ledger %s: utility move needs B2B on Daraja setup",
                    entry.pk,
                )
                return None
        else:
            client = DarajaClient(config)
            try:
                body, payload, shortcode = client.utility_to_working(
                    amount=entry.amount,
                    result_url=result_url,
                    timeout_url=timeout_url,
                )
            except DarajaError as exc:
                if dest_type == MoneyRequest.DestinationType.PHONE and config.b2c_ready:
                    logger.warning(
                        "Utility move failed for ledger %s (%s); trying B2C from working float.",
                        entry.pk,
                        exc,
                    )
                    wants_utility = False
                else:
                    logger.warning("Auto payout utility step failed for ledger %s: %s", entry.pk, exc)
                    return None
            else:
                meta = {
                    "auto_payout_ledger_id": entry.pk,
                    "auto_payout_chain": _chain_payload(monitor=monitor, entry=entry, phase="utility"),
                }
                with transaction.atomic():
                    return DarajaOperation.objects.create(
                        kind=DarajaOperation.Kind.B2B,
                        destination=shortcode,
                        amount=entry.amount,
                        account_ref="UTILITY-WORKING",
                        request_payload={**_redact(payload), **meta},
                        summary=body.get("ResponseDescription") or "Utility→working (auto payout step 1).",
                        collection_monitor=monitor,
                        **_ack_fields(body),
                    )

    if wants_utility:
        return None

    raw_dest = monitor_payout_destination(monitor)
    client = DarajaClient(config)

    try:
        if dest_type == MoneyRequest.DestinationType.PHONE:
            if not config.b2c_ready:
                logger.warning("Auto payout skipped for ledger %s: B2C not ready", entry.pk)
                return None
            phone = normalize_client_phone(raw_dest)
            body, payload, dest = client.b2c_send(
                phone=phone,
                amount=entry.amount,
                result_url=result_url,
                timeout_url=timeout_url,
            )
            kind = DarajaOperation.Kind.B2C
            account_ref = monitor.collection_code
        else:
            if not config.b2b_ready:
                logger.warning("Auto payout skipped for ledger %s: B2B not ready", entry.pk)
                return None
            to_till = dest_type == MoneyRequest.DestinationType.TILL
            body, payload, dest = client.b2b_send(
                destination=_digits(raw_dest),
                amount=entry.amount,
                to_till=to_till,
                account_ref=(monitor.auto_payout_account_ref or "").strip(),
                result_url=result_url,
                timeout_url=timeout_url,
            )
            kind = DarajaOperation.Kind.B2B
            account_ref = (monitor.auto_payout_account_ref or monitor.collection_code or "")[:64]
    except DarajaError as exc:
        logger.warning("Auto payout failed for ledger %s: %s", entry.pk, exc)
        return None

    meta = {
        "auto_payout_ledger_id": entry.pk,
        "auto_payout_chain": _chain_payload(monitor=monitor, entry=entry, phase="payout"),
        "auto_payout_source": "monitor",
    }
    with transaction.atomic():
        return DarajaOperation.objects.create(
            kind=kind,
            destination=dest,
            amount=entry.amount,
            account_ref=account_ref,
            request_payload={**_redact(payload), **meta},
            summary=body.get("ResponseDescription") or "Client auto payout queued.",
            collection_monitor=monitor,
            **_ack_fields(body),
        )


def continue_auto_payout_chain(operation: DarajaOperation) -> None:
    """After utility→working succeeds, run the configured paybill/till/phone payout."""
    chain = (operation.request_payload or {}).get("auto_payout_chain") or {}
    if chain.get("phase") != "utility":
        return
    if operation.status != DarajaOperation.Status.SUCCESS:
        return
    monitor_id = chain.get("monitor_id")
    ledger_id = chain.get("ledger_entry_id")
    if not monitor_id or not ledger_id:
        return
    monitor = CollectionMonitor.objects.filter(pk=monitor_id, is_active=True).first()
    entry = LedgerEntry.objects.filter(pk=ledger_id).first()
    if not monitor or not entry:
        return
    execute_auto_payout_transfer(monitor, entry, skip_utility=True)


def maybe_auto_payout_inbound(
    monitor: CollectionMonitor,
    entry: LedgerEntry,
) -> DarajaOperation | None:
    return execute_auto_payout_transfer(monitor, entry)


def schedule_auto_payout_inbound(monitor: CollectionMonitor, entry: LedgerEntry) -> None:
    if not auto_payout_is_enabled(monitor):
        return
    if entry.direction != LedgerEntry.Direction.IN:
        return
    if entry.status != LedgerEntry.Status.COMPLETED:
        return
    monitor_id = monitor.pk
    entry_id = entry.pk

    def _run() -> None:
        fresh_monitor = CollectionMonitor.objects.filter(pk=monitor_id, is_active=True).first()
        fresh_entry = LedgerEntry.objects.filter(pk=entry_id).first()
        if fresh_monitor and fresh_entry:
            maybe_auto_payout_inbound(fresh_monitor, fresh_entry)

    transaction.on_commit(_run)

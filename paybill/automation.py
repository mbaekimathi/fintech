"""Collection monitors: ledger totals and live Daraja balance per account."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from integrations.callbacks import balance_accounts_from_operation
from integrations.daraja import balance_operation_for_destination, callback_urls, request_hub_balance
from integrations.daraja_client import DarajaError, kenya_msisdn
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import CollectionMonitor, LedgerEntry


def monitor_ledger_queryset(monitor: CollectionMonitor):
    """Ledger rows for this collection account (paybill scope or collection ID tags)."""
    qs = LedgerEntry.objects.select_related(
        "paybill_account",
        "connected_system",
        "money_request",
        "money_request__requester",
    )

    if monitor.account_type in (
        CollectionMonitor.AccountType.PAYBILL,
        CollectionMonitor.AccountType.TILL,
    ):
        if monitor.paybill_account_id:
            return qs.filter(paybill_account_id=monitor.paybill_account_id)
        if monitor.identifier:
            return qs.filter(paybill_account__paybill_number=monitor.identifier)

    ref_filters = Q()
    if monitor.collection_code:
        ref_filters |= Q(account_ref=monitor.collection_code)
    if monitor.account_ref:
        ref_filters |= Q(account_ref=monitor.account_ref)
    if not ref_filters:
        return qs.none()

    scoped = qs.filter(ref_filters)
    if monitor.paybill_account_id:
        scoped = scoped.filter(paybill_account_id=monitor.paybill_account_id)
    elif monitor.account_type == CollectionMonitor.AccountType.PAYBILL:
        scoped = scoped.filter(paybill_account__paybill_number=monitor.identifier)
    return scoped


def monitor_ledger_totals(monitor: CollectionMonitor) -> dict:
    base = monitor_ledger_queryset(monitor).filter(status=LedgerEntry.Status.COMPLETED)
    inbound = base.filter(direction=LedgerEntry.Direction.IN).aggregate(s=Sum("amount"))["s"]
    outbound = base.filter(direction=LedgerEntry.Direction.OUT).aggregate(s=Sum("amount"))["s"]
    inbound = inbound if inbound is not None else Decimal("0")
    outbound = outbound if outbound is not None else Decimal("0")
    return {
        "inbound": inbound,
        "outbound": outbound,
        "net": inbound - outbound,
        "count": monitor_ledger_queryset(monitor).count(),
    }


def _ledger_collected(monitor: CollectionMonitor) -> Decimal:
    ref_filters = Q()
    if monitor.collection_code:
        ref_filters |= Q(account_ref=monitor.collection_code)
    if monitor.account_ref:
        ref_filters |= Q(account_ref=monitor.account_ref)
    if not ref_filters:
        return Decimal("0")

    qs = LedgerEntry.objects.filter(
        status=LedgerEntry.Status.COMPLETED,
        direction=LedgerEntry.Direction.IN,
    ).filter(ref_filters)

    if monitor.paybill_account_id:
        qs = qs.filter(paybill_account_id=monitor.paybill_account_id)
    elif monitor.account_type == CollectionMonitor.AccountType.PAYBILL:
        qs = qs.filter(paybill_account__paybill_number=monitor.identifier)
    total = qs.aggregate(s=Sum("amount"))["s"]
    return total if total is not None else Decimal("0")


def collection_stk_api_url(request=None) -> str:
    from django.urls import reverse

    path = reverse("integrations:collection-stk")
    if request is not None:
        return request.build_absolute_uri(path)
    from integrations.daraja import public_base_url

    base = public_base_url(request)
    return f"{base}{path}" if base else path


def collection_integration_copy(
    monitor: CollectionMonitor,
    *,
    stk_url: str,
    api_key: str = "",
) -> str:
    cred = monitor.credentials.filter(is_active=True).order_by("-created_at").first()
    if api_key:
        key_display = api_key
    elif cred:
        key_display = f"{cred.key_prefix}…  (replace with full cm_ key you saved at issue)"
    else:
        key_display = "cm_YOUR_KEY_HERE"

    body = '{"phone": "254712345678", "amount": "1500.00"}'
    return f"""NEXUS collection API — {monitor.label}

POST {stk_url}

Headers:
  X-API-Key: {key_display}
  Content-Type: application/json

Request body:
  {body}

Collection ID (C2B BillRefNumber; STK uses this automatically):
  {monitor.collection_code}

Paybill / till / phone on file:
  {monitor.display_identifier()} ({monitor.get_account_type_display()})

cURL:
curl -X POST "{stk_url}" \\
  -H "X-API-Key: {key_display if api_key else 'cm_YOUR_KEY_HERE'}" \\
  -H "Content-Type: application/json" \\
  -d '{body}'

JavaScript (fetch):
fetch("{stk_url}", {{
  method: "POST",
  headers: {{
    "X-API-Key": "{key_display if api_key else 'cm_YOUR_KEY_HERE'}",
    "Content-Type": "application/json",
  }},
  body: JSON.stringify({{ phone: "254712345678", amount: "1500.00" }}),
}});
"""


def serialize_collection_monitor_summary(
    monitor: CollectionMonitor,
    *,
    config: DarajaConfig | None = None,
) -> dict:
    """Lightweight row for the automations hub list (no live balance lookup)."""
    config = config or DarajaConfig.load()
    return {
        "id": monitor.pk,
        "label": monitor.label,
        "account_type_label": monitor.get_account_type_display(),
        "identifier": monitor.display_identifier(),
        "collection_code": monitor.collection_code or "",
        "collected_total": str(_ledger_collected(monitor)),
        "stk_ready": monitor.stk_ready(),
    }


def hub_company_snapshot(*, config: DarajaConfig | None = None) -> dict:
    config = config or DarajaConfig.load()
    paybill_name = ""
    if config.paybill_account_id:
        paybill_name = (config.paybill_account.account_name or "").strip()
    return {
        "environment": config.get_environment_display(),
        "environment_code": str(config.environment),
        "shortcode": (config.shortcode or "").strip(),
        "org_shortcode": (config.org_shortcode or "").strip(),
        "till_number": (config.till_number or "").strip(),
        "hub_paybill_name": paybill_name,
        "hub_paybill_number": (
            (config.paybill_account.paybill_number if config.paybill_account_id else "")
            or (config.shortcode or "").strip()
        ),
        "stk_ready": config.stk_ready,
        "balance_ready": config.balance_ready,
        "has_app_credentials": config.has_app_credentials,
    }


def serialize_collection_monitor(
    monitor: CollectionMonitor,
    *,
    config: DarajaConfig | None = None,
    request=None,
    fresh_api_key: str = "",
) -> dict:
    config = config or DarajaConfig.load()
    stk_url = collection_stk_api_url(request)
    cred = monitor.credentials.filter(is_active=True).order_by("-created_at").first()
    party_a = monitor.daraja_party_a()
    operation = balance_operation_for_destination(party_a)
    accounts = balance_accounts_from_operation(operation) if operation else {}
    working = accounts.get("working") or {}
    utility = accounts.get("utility") or {}
    summary = ""
    status = ""
    status_label = ""
    when = ""
    watch = False
    queued = False
    if operation is not None:
        summary = (operation.summary or operation.result_desc or "").strip()
        status = operation.status
        status_label = operation.get_status_display()
        when = timezone.localtime(operation.updated_at).strftime("%d %b %Y %H:%M")
        watch = operation.is_fresh_queue()
        queued = status == DarajaOperation.Status.QUEUED

    live_amount = working.get("amount")
    if live_amount is None:
        live_amount = utility.get("amount")
    live_currency = working.get("currency") or utility.get("currency") or "KES"

    return {
        "id": monitor.pk,
        "label": monitor.label,
        "account_type": monitor.account_type,
        "account_type_label": monitor.get_account_type_display(),
        "identifier": monitor.display_identifier(),
        "identifier_raw": monitor.identifier,
        "account_ref": monitor.account_ref or "",
        "collection_code": monitor.collection_code or "",
        "use_hub_daraja": monitor.use_hub_daraja,
        "has_own_daraja": monitor.has_own_daraja_credentials(),
        "stk_ready": monitor.stk_ready(),
        "credential_count": monitor.credentials.filter(is_active=True).count(),
        "api_key_prefix": cred.key_prefix if cred else "",
        "has_api_key": cred is not None,
        "stk_api_url": stk_url,
        "integration_copy": collection_integration_copy(
            monitor,
            stk_url=stk_url,
            api_key=fresh_api_key,
        ),
        "auto_refresh": monitor.auto_refresh,
        "collected_total": str(_ledger_collected(monitor)),
        "live_amount": live_amount,
        "live_currency": live_currency,
        "working_amount": working.get("amount"),
        "utility_amount": utility.get("amount"),
        "balance_summary": summary,
        "balance_status": status,
        "balance_status_label": status_label,
        "balance_when": when,
        "balance_watch": watch,
        "balance_queued": queued,
        "balance_ready": bool(config.balance_ready),
        "party_a": party_a,
    }


def request_monitor_balance(*, monitor: CollectionMonitor, request, created_by):
    config = DarajaConfig.load()
    if not config.balance_ready:
        raise DarajaError(
            "Live balance is not configured. Finish Balance setup under Daraja (initiator and result URLs)."
        )
    party_a = monitor.daraja_party_a()
    pending = balance_operation_for_destination(party_a, queued_only=True)
    if pending and pending.is_fresh_queue():
        return pending

    urls = callback_urls(request)
    return request_hub_balance(
        config=config,
        created_by=created_by,
        result_url=urls.get("result_url") or config.result_url,
        timeout_url=urls.get("timeout_url") or config.timeout_url,
        identifier=monitor.daraja_identifier_type(),
        party_a=party_a,
    )


def ensure_paybill_account(*, label: str, paybill_number: str):
    from paybill.models import PaybillAccount

    account, _ = PaybillAccount.objects.get_or_create(
        paybill_number=paybill_number,
        connected_system=None,
        defaults={
            "account_name": label[:160],
            "provider": PaybillAccount.Provider.MPESA,
        },
    )
    if label and account.account_name != label:
        account.account_name = label[:160]
        account.save(update_fields=["account_name"])
    return account


def normalize_monitor_identifier(account_type: str, raw: str) -> str:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if account_type == CollectionMonitor.AccountType.PHONE:
        return kenya_msisdn(raw)
    return digits

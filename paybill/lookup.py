"""Live destination name / business-name lookup for money requests."""

from __future__ import annotations

import re

from integrations.daraja_client import DarajaClient, DarajaError, kenya_msisdn
from integrations.models import DarajaConfig
from paybill.models import LedgerEntry, MoneyRequest, PaybillAccount

HAKIKISHA_SUCCESS = {"0", "00", "4000"}


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def phone_variants(raw: str) -> list[str]:
    digits = _digits(raw)
    variants: list[str] = []
    try:
        msisdn = kenya_msisdn(digits)
    except DarajaError:
        msisdn = ""
    for candidate in (
        digits,
        msisdn,
        ("0" + msisdn[3:]) if msisdn.startswith("254") and len(msisdn) == 12 else "",
        msisdn[3:] if msisdn.startswith("254") and len(msisdn) == 12 else "",
    ):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _format_ready(destination_type: str, destination: str) -> tuple[bool, str]:
    dest = _digits(destination)
    if destination_type == MoneyRequest.DestinationType.PHONE:
        try:
            kenya_msisdn(dest)
        except DarajaError as exc:
            return False, str(exc)
        return True, dest
    if dest.startswith("254") or len(dest) >= 10:
        return False, "That looks like a phone number. Choose Phone number, or enter a shortcode / till."
    if len(dest) < 5 or len(dest) > 8:
        label = "till" if destination_type == MoneyRequest.DestinationType.TILL else "paybill"
        return False, f"Enter a valid {label} number (5–8 digits)."
    return True, dest


def _name_from_payload(payload: dict) -> str:
    for key in (
        "OrganizationName",
        "organisationName",
        "organizationName",
        "CustomerName",
        "FullName",
        "Name",
        "AccountName",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:160]
    return ""


def _catalog_name(destination: str) -> str:
    row = (
        PaybillAccount.objects.filter(paybill_number=destination, is_active=True)
        .order_by("id")
        .first()
    )
    return (row.account_name or "").strip()[:160] if row else ""


def _history_phone_name(destination: str) -> str:
    variants = phone_variants(destination)
    if not variants:
        return ""
    prior = (
        MoneyRequest.objects.filter(
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination__in=variants,
        )
        .exclude(recipient_name="")
        .order_by("-created_at")
        .values_list("recipient_name", flat=True)
        .first()
    )
    if prior:
        return str(prior).strip()[:160]
    ledger = (
        LedgerEntry.objects.filter(payer_phone__in=variants)
        .exclude(payer_name="")
        .order_by("-posted_at")
        .values_list("payer_name", flat=True)
        .first()
    )
    return str(ledger or "").strip()[:160]


def _daraja_name(*, destination_type: str, destination: str) -> tuple[str, str]:
    """Return (name, detail). detail explains soft failures."""
    config = DarajaConfig.load()
    if not (config.consumer_key or "").strip() or not (config.consumer_secret or "").strip():
        return "", "Daraja credentials are not configured yet."
    client = DarajaClient(config)
    if destination_type == MoneyRequest.DestinationType.PHONE:
        try:
            msisdn = kenya_msisdn(destination)
        except DarajaError as exc:
            return "", str(exc)
        errors: list[str] = []
        for identifier_type in ("1", "2"):
            try:
                payload = client.hakikisha(identifier=msisdn, identifier_type=identifier_type)
                name = _name_from_payload(payload)
                if name:
                    return name, ""
            except DarajaError as exc:
                errors.append(str(exc))
        return "", (errors[-1] if errors else "No registered name returned for that phone.")
    try:
        payload = client.hakikisha(identifier=destination, identifier_type="4")
    except DarajaError as exc:
        return "", str(exc)
    name = _name_from_payload(payload)
    if name:
        return name, ""
    return "", "No registered business name returned for that shortcode."


def lookup_destination(*, destination_type: str, destination: str) -> dict:
    """Resolve a display name for a money-request destination.

    Preference order:
    1. Local paybill catalog (paybill / till)
    2. Daraja B2B Hakikisha
    3. Prior request / ledger history (phone)
    """
    dest_type = (destination_type or "").strip().upper()
    if dest_type not in MoneyRequest.DestinationType.values:
        return {
            "ok": False,
            "found": False,
            "name": "",
            "destination": "",
            "destination_type": dest_type,
            "source": "",
            "detail": "Choose phone, paybill, or till.",
        }

    ready, normalized_or_error = _format_ready(dest_type, destination)
    if not ready:
        return {
            "ok": False,
            "found": False,
            "name": "",
            "destination": _digits(destination),
            "destination_type": dest_type,
            "source": "",
            "detail": normalized_or_error,
        }

    normalized = normalized_or_error
    result = {
        "ok": True,
        "found": False,
        "name": "",
        "destination": normalized,
        "destination_type": dest_type,
        "source": "",
        "detail": "",
    }

    if dest_type in {
        MoneyRequest.DestinationType.PAYBILL,
        MoneyRequest.DestinationType.TILL,
    }:
        catalog = _catalog_name(normalized)
        if catalog:
            result.update(found=True, name=catalog, source="catalog", detail="")
            return result
        name, detail = _daraja_name(destination_type=dest_type, destination=normalized)
        if name:
            result.update(found=True, name=name, source="daraja", detail="")
            return result
        result["detail"] = detail or "Business name not found yet. You can still submit the request."
        return result

    name, detail = _daraja_name(destination_type=dest_type, destination=normalized)
    if name:
        result.update(found=True, name=name, source="daraja", detail="")
        return result
    history = _history_phone_name(normalized)
    if history:
        result.update(found=True, name=history, source="history", detail="")
        return result
    result["detail"] = detail or "Name not available for that phone yet. You can still submit the request."
    return result


def resolve_recipient_name(*, destination_type: str, destination: str) -> str:
    payload = lookup_destination(destination_type=destination_type, destination=destination)
    return (payload.get("name") or "").strip()[:160]

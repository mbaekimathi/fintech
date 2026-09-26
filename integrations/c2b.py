"""M-Pesa C2B (Pay Bill / Buy Goods) validation, confirmation, and URL registration."""

from __future__ import annotations

import re
import secrets
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from integrations.daraja import callback_urls, public_base_url
from integrations.daraja_client import DarajaClient, DarajaError, kenya_msisdn
from integrations.models import DarajaConfig
from paybill.models import CollectionMonitor, LedgerEntry, PaybillAccount


def normalize_c2b_payload(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return {}
    return {str(key).strip().lower(): value for key, value in data.items()}


def _digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def c2b_shortcodes_to_register() -> list[str]:
    codes: set[str] = set()
    config = DarajaConfig.load()
    if config.shortcode:
        codes.add(_digits(config.shortcode))
    for monitor in CollectionMonitor.objects.filter(is_active=True):
        if monitor.account_type in (
            CollectionMonitor.AccountType.PAYBILL,
            CollectionMonitor.AccountType.TILL,
        ):
            codes.add(_digits(monitor.identifier))
    return sorted(code for code in codes if code)


def c2b_callback_urls(request=None) -> dict:
    urls = callback_urls(request)
    return {
        "validation_url": urls.get("c2b_validation_url", ""),
        "confirmation_url": urls.get("c2b_confirmation_url", ""),
    }


def c2b_public_ready(request=None) -> tuple[bool, str]:
    urls = c2b_callback_urls(request)
    if not urls.get("validation_url") or not urls.get("confirmation_url"):
        base = public_base_url(request)
        if not base:
            return False, "Set a public HTTPS base (DARAJA_PUBLIC_BASE_URL or ngrok) so Safaricom can reach C2B callbacks."
        return False, "C2B callback URLs could not be built."
    config = DarajaConfig.load()
    if not config.has_app_credentials:
        return False, "Save Daraja consumer key, secret, and shortcode first."
    return True, ""


def resolve_monitor_by_collection_ref(bill_ref: str) -> CollectionMonitor | None:
    ref = (bill_ref or "").strip()
    if not ref:
        return None
    return (
        CollectionMonitor.objects.filter(is_active=True, collection_code=ref)
        .select_related("paybill_account")
        .first()
    )


def resolve_c2b_paybill_account(shortcode: str) -> PaybillAccount | None:
    code = _digits(shortcode)
    if not code:
        return None

    monitor = (
        CollectionMonitor.objects.filter(
            is_active=True,
            account_type__in=(
                CollectionMonitor.AccountType.PAYBILL,
                CollectionMonitor.AccountType.TILL,
            ),
            identifier=code,
        )
        .select_related("paybill_account")
        .first()
    )
    if monitor and monitor.paybill_account_id:
        return monitor.paybill_account

    account = PaybillAccount.objects.filter(paybill_number=code, is_active=True).first()
    if account:
        return account

    config = DarajaConfig.load()
    if config.paybill_account and _digits(config.paybill_account.paybill_number) == code:
        return config.paybill_account
    if _digits(config.shortcode) == code:
        if config.paybill_account:
            return config.paybill_account
        return PaybillAccount.objects.filter(paybill_number=code, is_active=True).first()
    return None


def is_shortcode_monitored(shortcode: str) -> bool:
    code = _digits(shortcode)
    if not code:
        return False
    if resolve_c2b_paybill_account(code):
        return True
    return CollectionMonitor.objects.filter(
        is_active=True,
        account_type__in=(
            CollectionMonitor.AccountType.PAYBILL,
            CollectionMonitor.AccountType.TILL,
        ),
        identifier=code,
    ).exists()


def validate_c2b_payment(payload: dict) -> dict:
    """Return Safaricom validation response body."""
    data = normalize_c2b_payload(payload)
    shortcode = data.get("businessshortcode") or data.get("shortcode") or ""
    if not is_shortcode_monitored(shortcode):
        return {
            "ResultCode": "C2B00012",
            "ResultDesc": "Shortcode is not registered for collection in NEXUS automations.",
        }
    amount_raw = data.get("transamount") or data.get("amount") or "0"
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError):
        return {"ResultCode": "C2B00013", "ResultDesc": "Invalid amount."}
    if amount < 1:
        return {"ResultCode": "C2B00013", "ResultDesc": "Amount must be at least KES 1."}
    trans_id = str(data.get("transid") or "").strip()
    third_party = trans_id[:20] if trans_id else secrets.token_hex(6)
    return {
        "ResultCode": 0,
        "ResultDesc": "Accepted",
        "ThirdPartyTransID": third_party,
    }


def is_duplicate_c2b_registration_error(message: str) -> bool:
    return "duplicate notification" in (message or "").lower()


def unique_c2b_bill_ref(proposed: str = "") -> str:
    """Avoid sandbox correlator collisions (e.g. repeated 123456)."""
    base = (proposed or "NEXUS").strip()[:32]
    suffix = secrets.token_hex(3).upper()
    combined = f"{base}-{suffix}"
    return combined[:64]


def post_c2b_ledger(payload: dict) -> LedgerEntry | None:
    """Create or update an inbound ledger row from a C2B confirmation callback."""
    data = normalize_c2b_payload(payload)
    trans_id = str(data.get("transid") or data.get("transactionid") or "").strip()[:64]
    if not trans_id:
        return None

    shortcode = data.get("businessshortcode") or data.get("shortcode") or ""
    bill_ref = str(data.get("billrefnumber") or data.get("accountreference") or "")[:64]
    monitor = resolve_monitor_by_collection_ref(bill_ref)
    account = None
    if monitor and monitor.paybill_account_id:
        account = monitor.paybill_account
    if account is None:
        account = resolve_c2b_paybill_account(shortcode)
    if account is None:
        return None

    amount_raw = data.get("transamount") or data.get("amount") or "0"
    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError):
        return None

    phone_raw = str(data.get("msisdn") or data.get("phonenumber") or "")
    try:
        phone = kenya_msisdn(phone_raw) if phone_raw else ""
    except DarajaError:
        phone = _digits(phone_raw)[:20]

    names = [
        str(data.get("firstname") or "").strip(),
        str(data.get("middlename") or "").strip(),
        str(data.get("lastname") or "").strip(),
    ]
    payer_name = " ".join(part for part in names if part)[:160]
    if not bill_ref and monitor:
        bill_ref = monitor.collection_code
    tx_type = str(data.get("transactiontype") or "C2B")[:64]

    existing = LedgerEntry.objects.filter(reference=trans_id).first()
    raw_payload = {"c2b": payload if isinstance(payload, dict) else data, "source": "daraja_c2b"}

    if existing is not None and existing.status == LedgerEntry.Status.COMPLETED:
        return existing

    if existing is not None:
        existing.amount = amount
        existing.payer_phone = phone or existing.payer_phone
        existing.payer_name = payer_name or existing.payer_name
        existing.account_ref = bill_ref or existing.account_ref
        existing.status = LedgerEntry.Status.COMPLETED
        existing.direction = LedgerEntry.Direction.IN
        existing.mpesa_reference = trans_id
        existing.narrative = f"{tx_type} · {shortcode}"[:255]
        existing.raw_payload = raw_payload
        existing.save(
            update_fields=[
                "amount",
                "payer_phone",
                "payer_name",
                "account_ref",
                "status",
                "direction",
                "mpesa_reference",
                "narrative",
                "raw_payload",
            ]
        )
        return existing

    return LedgerEntry.objects.create(
        reference=trans_id,
        mpesa_reference=trans_id,
        paybill_account=account,
        connected_system=account.connected_system,
        direction=LedgerEntry.Direction.IN,
        amount=amount,
        payer_name=payer_name,
        payer_phone=phone[:20],
        account_ref=bill_ref,
        status=LedgerEntry.Status.COMPLETED,
        narrative=f"{tx_type} · {shortcode}"[:255],
        raw_payload=raw_payload,
    )


def register_c2b_urls(*, request, shortcodes: list[str] | None = None) -> list[str]:
    """Register validation + confirmation URLs with Safaricom for each shortcode."""
    ready, detail = c2b_public_ready(request)
    if not ready:
        raise DarajaError(detail)

    config = DarajaConfig.load()
    urls = c2b_callback_urls(request)
    validation = urls["validation_url"]
    confirmation = urls["confirmation_url"]
    client = DarajaClient(config)
    response_type = (config.c2b_response_type or "Completed").strip() or "Completed"

    targets = shortcodes if shortcodes is not None else c2b_shortcodes_to_register()
    if not targets:
        raise DarajaError("Add a hub shortcode on Daraja setup or register at least one paybill/till monitor.")

    lines: list[str] = []
    for code in targets:
        try:
            body = client.register_c2b_urls(
                shortcode=code,
                validation_url=validation,
                confirmation_url=confirmation,
                response_type=response_type,
            )
        except DarajaError as exc:
            if is_duplicate_c2b_registration_error(str(exc)):
                lines.append(f"{code}: Already registered (Safaricom duplicate notification — OK).")
                continue
            raise
        desc = body.get("ResponseDescription") or body.get("CustomerMessage") or "Registered"
        lines.append(f"{code}: {desc}")

    summary = "; ".join(lines)
    config.c2b_registration_log = f"{timezone.localtime().strftime('%d %b %Y %H:%M')} — {summary}"[:2000]
    config.save(update_fields=["c2b_registration_log", "updated_at"])
    return lines


def simulate_c2b_payment(
    *,
    shortcode: str,
    amount,
    bill_ref: str,
    msisdn: str,
    command_id: str = "CustomerPayBillOnline",
) -> dict:
    config = DarajaConfig.load()
    if str(config.environment) != DarajaConfig.Environment.SANDBOX:
        raise DarajaError("C2B simulate is only available in sandbox.")
    if not config.has_app_credentials:
        raise DarajaError("Save Daraja app credentials first.")
    client = DarajaClient(config)
    return client.simulate_c2b(
        shortcode=_digits(shortcode),
        command_id=command_id,
        amount=amount,
        msisdn=msisdn,
        bill_ref=unique_c2b_bill_ref(bill_ref),
    )

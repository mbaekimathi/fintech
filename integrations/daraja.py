"""Safaricom Daraja sandbox defaults used for live-like local testing."""

import base64
import json
import urllib.error
import urllib.request

from paybill.models import PaybillAccount

SANDBOX_SHORTCODE = "174379"
SANDBOX_ORG_SHORTCODE = "600996"
SANDBOX_B2B_DESTINATION = "600000"
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
SANDBOX_INITIATOR = "testapi"
SANDBOX_INITIATOR_PASSWORD = "Safaricom123!!"
SANDBOX_TEST_PHONE = "254708374149"
SANDBOX_TEST_AMOUNT = "1"
SANDBOX_ACCOUNT_REF = "NEXUS"
SANDBOX_STK_DESC = "Payment"
SANDBOX_BALANCE_REMARKS = "Balance"
SANDBOX_B2C_REMARKS = "Payout"
SANDBOX_B2C_OCCASION = "Payment"
SANDBOX_B2B_REMARKS = "Transfer"

STK_CALLBACK_PATH = "/api/v1/daraja/stk/callback/"
RESULT_PATH = "/api/v1/daraja/result/"
TIMEOUT_PATH = "/api/v1/daraja/timeout/"

CALLBACK_URL_FIELDS = ("stk_callback_url", "result_url", "timeout_url")

SANDBOX_OAUTH_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
PRODUCTION_OAUTH_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
DARAJA_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NEXUS-Ledger/1.0"

SANDBOX_INSTANCE_FIELDS = (
    "shortcode",
    "org_shortcode",
    "passkey",
    "initiator_name",
    "security_credential",
    "stk_callback_url",
    "result_url",
    "timeout_url",
    "stk_account_reference",
    "stk_transaction_desc",
    "balance_remarks",
    "b2c_remarks",
    "b2c_occasion",
    "b2b_remarks",
)

# These differ per Daraja app. Autofill once; never overwrite what the user pasted.
SANDBOX_PORTAL_FIELDS = (
    "org_shortcode",
    "initiator_name",
    "security_credential",
)

# Older published sandbox values that should be replaced with the current portal pair.
SANDBOX_STALE = {
    "org_shortcode": {"", "600986"},
    "initiator_name": {""},
    "security_credential": {"", "Safaricom999!*!"},
}

SANDBOX_CHOICE_FIELDS = (
    "stk_transaction_type",
    "balance_identifier_type",
    "b2c_command_id",
    "b2b_sender_identifier_type",
    "b2b_paybill_command",
    "b2b_till_command",
)


def _is_public_https(url: str) -> bool:
    value = (url or "").strip().lower()
    return value.startswith("https://") and "localhost" not in value and "127.0.0.1" not in value


def detect_ngrok_base() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
    except Exception:
        return ""
    for tunnel in data.get("tunnels") or []:
        url = (tunnel.get("public_url") or "").rstrip("/")
        if _is_public_https(url):
            return url
    return ""


def public_base_url(request=None) -> str:
    from django.conf import settings as django_settings

    detected = detect_ngrok_base()
    if detected:
        return detected
    configured = (getattr(django_settings, "DARAJA_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if _is_public_https(configured):
        return configured
    if request is not None:
        origin = request.build_absolute_uri("/").rstrip("/")
        if _is_public_https(origin):
            return origin
    return ""


def callback_urls(request=None) -> dict:
    base = public_base_url(request)
    if not base:
        return {}
    return {
        "stk_callback_url": base + STK_CALLBACK_PATH,
        "result_url": base + RESULT_PATH,
        "timeout_url": base + TIMEOUT_PATH,
    }


def ensure_sandbox_paybill() -> PaybillAccount:
    account = PaybillAccount.objects.filter(paybill_number=SANDBOX_SHORTCODE).first()
    if account:
        return account
    return PaybillAccount.objects.create(
        paybill_number=SANDBOX_SHORTCODE,
        account_name="Daraja sandbox test paybill",
        provider=PaybillAccount.Provider.MPESA,
        short_code_notes="Safaricom Lipa Na M-Pesa Online sandbox (174379)",
        is_active=True,
    )


def sandbox_defaults_payload(request=None) -> dict:
    origin = public_base_url(request) or (
        request.build_absolute_uri("/").rstrip("/") if request is not None else "http://localhost:8000"
    )
    host = origin.split("//", 1)[-1].split(":")[0].split("/")[0]
    paybill_ids = {
        row.paybill_number: row.pk
        for row in PaybillAccount.objects.filter(is_active=True)
    }
    return {
        "shortcode": SANDBOX_SHORTCODE,
        "org_shortcode": SANDBOX_ORG_SHORTCODE,
        "passkey": SANDBOX_PASSKEY,
        "initiator_name": SANDBOX_INITIATOR,
        "security_credential": SANDBOX_INITIATOR_PASSWORD,
        "test_phone": SANDBOX_TEST_PHONE,
        "test_amount": SANDBOX_TEST_AMOUNT,
        "stk_callback_url": origin + STK_CALLBACK_PATH,
        "result_url": origin + RESULT_PATH,
        "timeout_url": origin + TIMEOUT_PATH,
        "stk_transaction_type": "CustomerPayBillOnline",
        "stk_account_reference": SANDBOX_ACCOUNT_REF,
        "stk_transaction_desc": SANDBOX_STK_DESC,
        "balance_identifier_type": "4",
        "balance_remarks": SANDBOX_BALANCE_REMARKS,
        "b2c_enabled": True,
        "b2c_command_id": "BusinessPayment",
        "b2c_remarks": SANDBOX_B2C_REMARKS,
        "b2c_occasion": SANDBOX_B2C_OCCASION,
        "b2b_enabled": True,
        "b2b_sender_identifier_type": "4",
        "b2b_paybill_command": "BusinessPayBill",
        "b2b_till_command": "BusinessBuyGoods",
        "b2b_remarks": SANDBOX_B2B_REMARKS,
        "paybill_ids": paybill_ids,
        "is_local": host in {"localhost", "127.0.0.1"},
        "public_base_url": public_base_url(request),
    }


def apply_sandbox_to_instance(obj, request, *, force: bool = True) -> None:
    """Fill sandbox STK/callback defaults. Portal initiator fields fill only when empty."""
    if str(obj.environment) != obj.Environment.SANDBOX:
        return
    payload = sandbox_defaults_payload(request)
    for field in SANDBOX_INSTANCE_FIELDS:
        current = str(getattr(obj, field, "") or "").strip()
        if field in CALLBACK_URL_FIELDS and _is_public_https(current) and not payload.get("public_base_url"):
            continue
        if field in SANDBOX_PORTAL_FIELDS:
            stale = SANDBOX_STALE.get(field, {""})
            if current in stale:
                setattr(obj, field, payload[field])
            continue
        if force or not current:
            setattr(obj, field, payload[field])
    for field in SANDBOX_CHOICE_FIELDS:
        current = str(getattr(obj, field, "") or "").strip()
        if force or not current:
            setattr(obj, field, payload[field])
    obj.b2c_enabled = True
    obj.b2b_enabled = True
    if not obj.paybill_account_id:
        obj.paybill_account = ensure_sandbox_paybill()


def _waf_blocked(status: int, body: str) -> bool:
    text = (body or "").lower()
    return status in {403, 429} and (
        "incapsula" in text
        or "_incapsula_resource" in text
        or "iframe" in text
        or not text.strip().startswith("{")
    )


def probe_daraja(config) -> dict:
    """Ask Daraja for an access token using the saved consumer key and secret."""
    key = (config.consumer_key or "").strip()
    secret = (config.consumer_secret or "").strip()
    if not key or not secret:
        return {
            "ok": False,
            "state": "missing_keys",
            "title": "Not integrated",
            "detail": "Paste your Daraja consumer key and secret, then save.",
        }
    url = SANDBOX_OAUTH_URL if str(config.environment) == "SANDBOX" else PRODUCTION_OAUTH_URL
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "User-Agent": DARAJA_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if _waf_blocked(exc.code, raw):
            return {
                "ok": False,
                "state": "waf",
                "title": "Connection check blocked",
                "detail": "Safaricom's firewall blocked the token check (HTTP 403). Your consumer key and secret are saved — this is not a bad-key error. Refresh in a few seconds.",
            }
        return {
            "ok": False,
            "state": "rejected",
            "title": "Not integrated",
            "detail": f"Safaricom rejected these app credentials (HTTP {exc.code}). Check the consumer key and secret.",
        }
    except Exception:
        return {
            "ok": False,
            "state": "unreachable",
            "title": "Not integrated",
            "detail": "Could not reach Daraja. Check your internet connection and try again.",
        }
    if body.get("access_token"):
        env = "sandbox" if str(config.environment) == "SANDBOX" else "production"
        return {
            "ok": True,
            "state": "connected",
            "title": "Successfully integrated",
            "detail": f"Daraja accepted this consumer key and secret on {env}.",
        }
    return {
        "ok": False,
        "state": "rejected",
        "title": "Not integrated",
        "detail": "Daraja did not return an access token for these credentials.",
    }


def sandbox_field_checks(config, request=None) -> list[dict]:
    payload = sandbox_defaults_payload(request)
    pairs = [
        ("Paybill shortcode", "shortcode"),
        ("Organization shortcode", "org_shortcode"),
        ("Lipa Na M-Pesa passkey", "passkey"),
        ("Initiator username", "initiator_name"),
        ("Security credential", "security_credential"),
        ("STK callback URL", "stk_callback_url"),
        ("Result URL", "result_url"),
        ("Timeout URL", "timeout_url"),
        ("STK transaction type", "stk_transaction_type"),
        ("STK account reference", "stk_account_reference"),
        ("STK description", "stk_transaction_desc"),
        ("Balance identifier", "balance_identifier_type"),
        ("B2C command", "b2c_command_id"),
        ("B2B paybill command", "b2b_paybill_command"),
        ("B2B till command", "b2b_till_command"),
    ]
    checks = []
    for label, field in pairs:
        expected = str(payload.get(field, "") or "")
        actual = str(getattr(config, field, "") or "").strip()
        if field in SANDBOX_PORTAL_FIELDS:
            checks.append(
                {
                    "label": label,
                    "ok": bool(actual),
                    "expected": "From your Daraja Test credentials page",
                }
            )
            continue
        checks.append({"label": label, "ok": actual == expected, "expected": expected})
    checks.append({"label": "Hub paybill", "ok": bool(config.paybill_account_id), "expected": "Sandbox test paybill"})
    checks.append({"label": "B2C enabled", "ok": bool(config.b2c_enabled), "expected": "On"})
    checks.append({"label": "B2B enabled", "ok": bool(config.b2b_enabled), "expected": "On"})
    checks.append(
        {
            "label": "Consumer key",
            "ok": bool((config.consumer_key or "").strip()),
            "expected": "From your Daraja sandbox app",
        }
    )
    checks.append(
        {
            "label": "Consumer secret",
            "ok": bool((config.consumer_secret or "").strip()),
            "expected": "From your Daraja sandbox app",
        }
    )
    return checks


def integration_status(config, request=None) -> dict:
    probe = probe_daraja(config)
    checks = []
    fields_ok = True
    if str(config.environment) == "SANDBOX":
        checks = sandbox_field_checks(config, request)
        fields_ok = all(item["ok"] for item in checks)
    integrated = bool(probe["ok"] and fields_ok)
    if probe["state"] == "waf" and fields_ok:
        integrated = True
        title = "Credentials saved"
        detail = probe["detail"]
    elif integrated:
        title = "Successfully integrated"
        detail = probe["detail"]
    elif probe["state"] == "missing_keys":
        title = "Not integrated"
        detail = probe["detail"]
    elif not fields_ok:
        title = "Not integrated"
        detail = "Sandbox test values are on this form. Save them, then paste your consumer key and secret."
    else:
        title = probe["title"]
        detail = probe["detail"]
    return {
        "integrated": integrated,
        "probe": probe,
        "checks": checks,
        "title": title,
        "detail": detail,
    }

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
AGENT_DEPOSIT_CALLBACK_PATH = "/api/v1/daraja/agent/deposit/callback/"
AGENT_WITHDRAW_CALLBACK_PATH = "/api/v1/daraja/agent/withdraw/callback/"
AGENT_RESULT_PATH = "/api/v1/daraja/agent/result/"
AGENT_TIMEOUT_PATH = "/api/v1/daraja/agent/timeout/"

CALLBACK_URL_FIELDS = (
    "stk_callback_url",
    "result_url",
    "timeout_url",
    "agent_deposit_callback_url",
    "agent_withdraw_callback_url",
    "agent_result_url",
    "agent_timeout_url",
)

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


def hosted_base_url(request=None) -> str:
    """Live site Safaricom should call. Never localhost."""
    from django.conf import settings as django_settings

    configured = (getattr(django_settings, "DARAJA_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if _is_public_https(configured):
        return configured
    for host in getattr(django_settings, "ALLOWED_HOSTS", []) or []:
        host = (host or "").strip().lstrip(".")
        if not host or host in {"localhost", "127.0.0.1", "testserver", "*"}:
            continue
        if "ngrok" in host.lower():
            continue
        return f"https://{host}"
    if request is not None:
        origin = request.build_absolute_uri("/").rstrip("/")
        if _is_public_https(origin):
            return origin
    return "https://fin.richcom.co.ke"


def public_base_url(request=None) -> str:
    from django.conf import settings as django_settings

    configured = (getattr(django_settings, "DARAJA_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if _is_public_https(configured):
        return configured
    if request is not None:
        origin = request.build_absolute_uri("/").rstrip("/")
        if _is_public_https(origin):
            return origin
    detected = detect_ngrok_base()
    if detected:
        return detected
    return hosted_base_url(request)


def callback_urls(request=None) -> dict:
    base = public_base_url(request)
    if not base:
        return {}
    return {
        "stk_callback_url": base + STK_CALLBACK_PATH,
        "result_url": base + RESULT_PATH,
        "timeout_url": base + TIMEOUT_PATH,
        "agent_deposit_callback_url": base + AGENT_DEPOSIT_CALLBACK_PATH,
        "agent_withdraw_callback_url": base + AGENT_WITHDRAW_CALLBACK_PATH,
        "agent_result_url": base + AGENT_RESULT_PATH,
        "agent_timeout_url": base + AGENT_TIMEOUT_PATH,
    }


def hub_balance_operation(config, *, queued_only: bool = False):
    """Latest account-balance query for the configured organization shortcode."""
    from integrations.models import DarajaOperation

    shortcode = str(config.payout_shortcode or "")
    qs = DarajaOperation.objects.filter(kind=DarajaOperation.Kind.BALANCE)
    if shortcode:
        qs = qs.filter(destination=shortcode)
    if queued_only:
        qs = qs.filter(status=DarajaOperation.Status.QUEUED)
    return qs.order_by("-created_at").first()


def serialize_hub_balance(config, operation=None) -> dict:
    from django.utils import timezone

    from integrations.callbacks import balance_accounts_from_operation
    from integrations.models import DarajaOperation

    if operation is None:
        operation = hub_balance_operation(config)
    paybill = config.paybill_account
    summary = ""
    status = ""
    status_label = ""
    when = ""
    watch = False
    operation_id = None
    accounts = {}
    if operation is not None:
        summary = (operation.summary or operation.result_desc or "").strip()
        status = operation.status
        status_label = operation.get_status_display()
        when = timezone.localtime(operation.created_at).strftime("%d %b %Y %H:%M")
        watch = operation.is_fresh_queue()
        operation_id = operation.pk
        accounts = balance_accounts_from_operation(operation)
    from integrations.daraja_errors import utility_transfer_blockers

    utility = accounts.get("utility") or {}
    working = accounts.get("working") or {}
    transfer_blockers = utility_transfer_blockers(config)
    return {
        "ready": bool(config.balance_ready),
        "transfer_ready": bool(config.b2b_enabled and config.balance_ready and not transfer_blockers),
        "transfer_blockers": transfer_blockers,
        "paybill_name": paybill.account_name if paybill else "",
        "paybill_number": paybill.paybill_number if paybill else "",
        "shortcode": config.payout_shortcode or "",
        "status": status,
        "status_label": status_label,
        "summary": summary,
        "when": when,
        "watch": watch,
        "operation_id": operation_id,
        "queued": status == DarajaOperation.Status.QUEUED,
        "accounts": accounts,
        "utility_amount": utility.get("amount"),
        "utility_currency": utility.get("currency") or "KES",
        "working_amount": working.get("amount"),
        "working_currency": working.get("currency") or "KES",
    }


def request_hub_balance(*, config, created_by, result_url: str, timeout_url: str, identifier=None):
    """Queue a live account-balance query against Safaricom."""
    from integrations.daraja_client import DarajaClient, DarajaError
    from integrations.models import DarajaOperation

    if not config.balance_ready:
        raise DarajaError("Live balance is not configured yet.")
    if not result_url or not timeout_url:
        raise DarajaError("Set HTTPS result and timeout URLs on Daraja setup first.")

    client = DarajaClient(config)
    body, payload, party_a = client.account_balance(
        result_url=result_url,
        timeout_url=timeout_url,
        identifier=str(identifier or config.balance_identifier_type or "4"),
    )
    return DarajaOperation.objects.create(
        kind=DarajaOperation.Kind.BALANCE,
        destination=party_a,
        request_payload=_redact_daraja_payload(payload),
        summary=body.get("ResponseDescription") or "Balance requested. Waiting for Daraja result.",
        merchant_request_id=body.get("MerchantRequestID") or "",
        checkout_request_id=body.get("CheckoutRequestID") or "",
        conversation_id=body.get("ConversationID") or "",
        originator_conversation_id=body.get("OriginatorConversationID") or "",
        result_desc=(body.get("ResponseDescription") or body.get("CustomerMessage") or "")[:255],
        response_payload=body,
        created_by=created_by,
    )


def _redact_daraja_payload(payload: dict) -> dict:
    data = dict(payload or {})
    for key in ("SecurityCredential", "Password"):
        if key in data:
            data[key] = "[redacted]"
    return data


def form_callback_urls(request=None) -> dict:
    """Always fill the setup form with the hosted HTTPS callbacks."""
    base = hosted_base_url(request)
    return {
        "stk_callback_url": base + STK_CALLBACK_PATH,
        "result_url": base + RESULT_PATH,
        "timeout_url": base + TIMEOUT_PATH,
        "agent_deposit_callback_url": base + AGENT_DEPOSIT_CALLBACK_PATH,
        "agent_withdraw_callback_url": base + AGENT_WITHDRAW_CALLBACK_PATH,
        "agent_result_url": base + AGENT_RESULT_PATH,
        "agent_timeout_url": base + AGENT_TIMEOUT_PATH,
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
    hosted = hosted_base_url(request)
    urls = form_callback_urls(request)
    origin = hosted
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
        "stk_callback_url": urls["stk_callback_url"],
        "result_url": urls["result_url"],
        "timeout_url": urls["timeout_url"],
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
        "is_local": False,
        "public_base_url": hosted,
        "form_urls": urls,
        "channel_paybill": {
            "stk_transaction_type": "CustomerPayBillOnline",
            "balance_identifier_type": "4",
            "b2b_sender_identifier_type": "4",
        },
        "channel_till": {
            "stk_transaction_type": "CustomerBuyGoodsOnline",
            "balance_identifier_type": "2",
            "b2b_sender_identifier_type": "2",
        },
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


def _request_host(request) -> str:
    if request is None:
        return ""
    return (request.get_host() or "").split(":")[0].strip().lower()


def _browsing_locally(request) -> bool:
    return _request_host(request) in {"localhost", "127.0.0.1"}


def _latest_operations() -> dict:
    from integrations.models import DarajaOperation

    latest = {}
    for row in DarajaOperation.objects.all()[:40]:
        if row.kind in latest:
            continue
        latest[row.kind] = {
            "status": row.status,
            "status_label": row.get_status_display(),
            "summary": (row.summary or row.result_desc or "").strip(),
            "when": row.created_at,
        }
        if len(latest) >= 4:
            break
    return latest


def _op_note(last: dict | None) -> str:
    if not last:
        return "Not tested yet on this page."
    summary = last.get("summary") or last.get("status_label") or last.get("status")
    return f"Last test: {last.get('status_label') or last.get('status')}. {summary}".strip()


def _timed_out(last: dict | None) -> bool:
    return bool(last and last.get("status") == "TIMEOUT")


def callback_reachability(request=None, config=None) -> dict:
    """Whether Safaricom can POST results back to the hub that is serving this page."""
    ngrok = detect_ngrok_base()
    hosted = hosted_base_url(request)
    live = public_base_url(request)
    urls = callback_urls(request) if live else {}
    local = _browsing_locally(request)
    live_ok = _is_public_https(live)
    live_is_ngrok = "ngrok" in (live or "").lower()
    if local:
        ready = bool(ngrok and live_ok and live_is_ngrok)
        if ready:
            detail = f"ngrok is forwarding Safaricom callbacks to this machine ({live})."
        elif ngrok and live_ok and not live_is_ngrok:
            detail = (
                f"ngrok is running at {ngrok}, but this hub will still tell Safaricom to POST to {live}. "
                "Set DARAJA_PUBLIC_BASE_URL to the ngrok https URL so balance and payout results land here."
            )
        else:
            detail = (
                f"You are on localhost and ngrok is not in use. Safaricom will POST results to {live or hosted}, "
                "not this page. Run ngrok http 8000, set DARAJA_PUBLIC_BASE_URL to that https URL, then refresh."
            )
    else:
        ready = live_ok
        detail = (
            f"Safaricom will POST results to {live}."
            if ready
            else "No public HTTPS callback URL. Set DARAJA_PUBLIC_BASE_URL or open this hub on its https host."
        )
    blockers = [] if ready else [detail]
    if config is not None:
        stored = [
            ("STK callback", getattr(config, "stk_callback_url", "")),
            ("Result URL", getattr(config, "result_url", "")),
            ("Timeout URL", getattr(config, "timeout_url", "")),
        ]
        for label, value in stored:
            if value and not _is_public_https(value):
                blockers.append(f"{label} is not public HTTPS.")
                ready = False
    return {
        "ready": ready,
        "detail": detail,
        "blockers": blockers,
        "ngrok": ngrok,
        "hosted": hosted,
        "live": live,
        "urls": urls,
        "local": local,
    }


def _capability(
    *,
    cap_id: str,
    name: str,
    work: str,
    ready: bool,
    detail: str,
    blockers: list[str] | None = None,
    last: dict | None = None,
    timeout_blocks: bool = True,
) -> dict:
    notes = list(dict.fromkeys(blockers or []))
    if timeout_blocks and _timed_out(last):
        ready = False
        timeout_note = (
            "Last test timed out. Safaricom accepted the request but never reached this hub's result URL."
        )
        if timeout_note not in notes:
            notes.append(timeout_note)
        if not detail:
            detail = timeout_note
    return {
        "id": cap_id,
        "name": name,
        "work": work,
        "ready": ready,
        "detail": detail,
        "blockers": notes,
        "last": last,
        "last_note": _op_note(last),
    }


def capability_status(config, request=None) -> dict:
    """What is ready to run from the test page versus what is still incomplete."""
    status = integration_status(config, request)
    probe = status["probe"]
    oauth_ok = bool(probe.get("ok") or probe.get("state") == "waf")
    callbacks = callback_reachability(request, config)
    last = _latest_operations()

    oauth_blockers = [] if oauth_ok else [probe.get("detail") or "Daraja did not accept these app credentials."]
    stk_blockers = []
    if not config.has_app_credentials:
        stk_blockers.append("Save consumer key, consumer secret, and the Lipa Na M-Pesa shortcode.")
    if not (config.passkey or "").strip():
        stk_blockers.append("Save the Lipa Na M-Pesa Online passkey.")
    if not _is_public_https(config.stk_callback_url) and not _is_public_https(
        (callbacks.get("urls") or {}).get("stk_callback_url", "")
    ):
        stk_blockers.append("STK callback URL must be public HTTPS.")
    if not oauth_ok:
        stk_blockers.extend(oauth_blockers)

    initiator_blockers = []
    if not (config.initiator_name or "").strip():
        initiator_blockers.append("Paste the initiator username from Daraja Test credentials (not the STK till).")
    if not (config.security_credential or "").strip():
        initiator_blockers.append("Paste the initiator password / security credential.")
    if not (config.payout_shortcode or "").strip():
        initiator_blockers.append("Set organization shortcode (sandbox Party A is 600996).")
    if not callbacks["ready"]:
        initiator_blockers.extend(callbacks["blockers"])
    if not oauth_ok:
        initiator_blockers.extend(oauth_blockers)

    b2c_blockers = list(initiator_blockers)
    if not config.b2c_enabled:
        b2c_blockers.append("Turn on B2C on Daraja setup, and enable Account Balance + B2C on the Daraja app.")
    if not (config.b2c_command_id or "").strip():
        b2c_blockers.append("Choose a B2C command (Business payment).")

    b2b_blockers = list(initiator_blockers)
    if not config.b2b_enabled:
        b2b_blockers.append("Turn on B2B on Daraja setup, and enable B2B on the Daraja app.")
    if not (config.b2b_paybill_command and config.b2b_till_command):
        b2b_blockers.append("Save B2B paybill and till commands.")

    stk_ready = bool(config.stk_ready and oauth_ok)
    balance_ready = bool(config.balance_ready and oauth_ok and callbacks["ready"])
    b2c_ready = bool(config.b2c_ready and oauth_ok and callbacks["ready"])
    b2b_ready = bool(config.b2b_ready and oauth_ok and callbacks["ready"])

    capabilities = [
        _capability(
            cap_id="oauth",
            name="Daraja app login",
            work="Safaricom accepts this consumer key and secret and can issue an access token.",
            ready=oauth_ok,
            detail=probe.get("detail") or "",
            blockers=oauth_blockers,
        ),
        _capability(
            cap_id="callbacks",
            name="Result callbacks to this hub",
            work="After PIN, balance, or a payout, Safaricom POSTs the result to this hub.",
            ready=callbacks["ready"],
            detail=callbacks["detail"],
            blockers=callbacks["blockers"],
            last=last.get("BALANCE") or last.get("B2C") or last.get("B2B"),
        ),
        _capability(
            cap_id="stk",
            name="STK push",
            work="Prompt a customer phone to pay into this shortcode. Refresh can query status if the callback is delayed.",
            ready=stk_ready,
            detail="Ready to send an STK prompt." if stk_ready else "STK is not ready to send.",
            blockers=stk_blockers,
            last=last.get("STK"),
            timeout_blocks=False,
        ),
        _capability(
            cap_id="balance",
            name="Account balance",
            work="Ask Safaricom for the live float on the organization shortcode. Needs a result callback.",
            ready=balance_ready,
            detail="Ready to request live float." if balance_ready else "Balance is not ready to run from this page.",
            blockers=initiator_blockers,
            last=last.get("BALANCE"),
        ),
        _capability(
            cap_id="b2c",
            name="Send to a phone (B2C)",
            work="Pay out from the organization shortcode to a Kenyan mobile number.",
            ready=b2c_ready,
            detail="Ready to send to a phone." if b2c_ready else "Phone payout is not ready to run from this page.",
            blockers=b2c_blockers,
            last=last.get("B2C"),
        ),
        _capability(
            cap_id="b2b",
            name="Send to paybill or till (B2B)",
            work="Pay out from the organization shortcode to another paybill or till.",
            ready=b2b_ready,
            detail="Ready to send to a paybill or till." if b2b_ready else "Paybill/till payout is not ready to run from this page.",
            blockers=b2b_blockers,
            last=last.get("B2B"),
        ),
    ]
    if config.agent_shop_enabled:
        agent_blockers = []
        if config.is_safaricom_agent_channel:
            if not config.agent_api_enabled:
                agent_blockers.append("Turn on official agent APIs after Safaricom issues access.")
            if not (config.agent_till_number or "").strip():
                agent_blockers.append("Save the agent till number from Safaricom.")
            if not config.agent_app_credentials_ready:
                agent_blockers.append("Finish Daraja app credentials, or paste a separate agent app key/secret.")
            if not config.agent_safaricom_config_ready:
                agent_blockers.append("Save agent callback URLs (deposit, withdraw, result, timeout).")
            if not (config.agent_deposit_path and config.agent_withdraw_path):
                agent_blockers.append("Paste deposit/withdraw API paths when Safaricom sends the pack (optional until then).")
            detail = (
                "Official agent config is ready for wiring."
                if config.agent_shop_ready
                else "Official Safaricom agent channel needs till, APIs, and callbacks."
            )
            work = "Deposit and withdraw for clients on an official agent till, with Safaricom commission when exposed."
        else:
            if config.agent_cash_in_enabled and not stk_ready:
                agent_blockers.extend(stk_blockers or ["Finish STK setup for cash-in."])
            if config.agent_cash_out_enabled and not b2c_ready:
                agent_blockers.extend(b2c_blockers or ["Finish B2C setup for cash-out."])
            detail = (
                "Agent shop logic is ready."
                if config.agent_shop_ready
                else "Agent shop is on but cash-in/out is not ready."
            )
            work = "Cash-in from a phone (STK) and cash-out to a phone (B2C) with shop limits and fees."
        if not config.agent_cash_in_enabled and not config.agent_cash_out_enabled:
            agent_blockers.append("Turn on deposit, withdraw, or both.")
        agent_ready = bool(config.agent_shop_ready and (oauth_ok or config.is_safaricom_agent_channel))
        if config.is_safaricom_agent_channel and config.agent_use_shared_app and not oauth_ok:
            agent_ready = False
            agent_blockers.extend(oauth_blockers)
        capabilities.append(
            _capability(
                cap_id="agent",
                name="Agent shop",
                work=work,
                ready=agent_ready,
                detail=detail,
                blockers=agent_blockers,
            )
        )
    ready = [item for item in capabilities if item["ready"]]
    not_ready = [item for item in capabilities if not item["ready"]]
    ready_count = len(ready)
    total = len(capabilities)
    if ready_count == total:
        title = "All capabilities are ready to work"
        detail = status["detail"] if status["integrated"] else "Each Daraja action on this page can run."
    elif ready_count:
        title = f"{ready_count} of {total} capabilities ready to work"
        detail = "Use the ready actions below. Fix the items that are not well integrated before relying on them."
    else:
        title = "Nothing is ready to work yet"
        detail = status["detail"]
    return {
        **status,
        "title": title,
        "detail": detail,
        "capabilities": capabilities,
        "by_id": {item["id"]: item for item in capabilities},
        "ready": ready,
        "not_ready": not_ready,
        "ready_count": ready_count,
        "total": total,
        "callbacks": callbacks,
        "fully_ready": ready_count == total,
    }


def panel_blockers(integration: dict, cap_id: str) -> list[str]:
    """Per-test blockers with shared app/callback issues shown once at page top."""
    cap = integration["by_id"][cap_id]
    blockers = list(cap["blockers"])
    by_id = integration["by_id"]
    if not by_id["oauth"]["ready"]:
        drop = set(by_id["oauth"]["blockers"])
        blockers = [item for item in blockers if item not in drop]
    if cap_id in ("balance", "b2c", "b2b") and not by_id["callbacks"]["ready"]:
        drop = set(by_id["callbacks"]["blockers"])
        blockers = [item for item in blockers if item not in drop]
    if not cap["ready"] and not blockers:
        if not by_id["oauth"]["ready"]:
            blockers = ["Fix Daraja app login first (see above)."]
        elif cap_id in ("balance", "b2c", "b2b") and not by_id["callbacks"]["ready"]:
            blockers = ["Fix the public callback URL first (see above)."]
        elif cap.get("detail"):
            blockers = [cap["detail"]]
        else:
            blockers = ["Finish this section on Daraja setup."]
    return blockers

"""One-time SMS codes for payment approval (PIN on approve)."""

from __future__ import annotations

import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from core.approval import (
    approval_phone_stk_enabled,
    stk_pin_approval_required,
    user_requires_stk_on_approval,
)
from core.models import ApprovalSmsChallenge
from integrations.daraja_client import DarajaError, kenya_msisdn

logger = logging.getLogger(__name__)

OTP_TTL = timedelta(minutes=10)
MAX_SENDS_PER_WINDOW = 5
SEND_WINDOW = timedelta(minutes=15)


def approval_sms_otp_enabled() -> bool:
    """SMS one-time code to the reviewer's phone when hub PIN-on-approve is on (no Lipa STK)."""
    if not stk_pin_approval_required():
        return False
    if approval_phone_stk_enabled():
        return False
    return bool(getattr(django_settings, "APPROVAL_SMS_OTP", True))


def _otp_ttl() -> timedelta:
    minutes = getattr(django_settings, "APPROVAL_SMS_OTP_TTL_MINUTES", 10)
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        minutes = 10
    return timedelta(minutes=max(3, min(minutes, 30)))


def mask_phone(msisdn: str) -> str:
    digits = "".join(ch for ch in msisdn if ch.isdigit())
    if len(digits) < 4:
        return "your phone"
    return f"***{digits[-4:]}"


def _send_sms_message(*, to_msisdn: str, message: str) -> None:
    provider = (getattr(django_settings, "SMS_PROVIDER", None) or "console").strip().lower()
    if provider == "console":
        logger.info("SMS (console) to %s: %s", to_msisdn, message)
        return

    if provider == "africastalking":
        username = (getattr(django_settings, "AFRICASTALKING_USERNAME", None) or "").strip()
        api_key = (getattr(django_settings, "AFRICASTALKING_API_KEY", None) or "").strip()
        if not username or not api_key:
            raise DarajaError(
                "SMS is not configured. Set AFRICASTALKING_USERNAME and AFRICASTALKING_API_KEY in .env."
            )
        body = urllib.parse.urlencode({"username": username, "to": to_msisdn, "message": message})
        req = urllib.request.Request(
            "https://api.africastalking.com/version1/messaging",
            data=body.encode("utf-8"),
            headers={
                "apiKey": api_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise DarajaError(f"Could not send SMS ({exc.code}): {detail[:200]}") from exc
        except urllib.error.URLError as exc:
            raise DarajaError(f"Could not reach SMS provider: {exc.reason}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        recipients = (payload.get("SMSMessageData") or {}).get("Recipients") or []
        for row in recipients:
            status = (row.get("status") or "").strip()
            if status and status.upper() not in {"SUCCESS", "SENT", "SUBMITTED"}:
                raise DarajaError(row.get("status") or "SMS was not accepted.")
        return

    raise DarajaError(f"Unknown SMS_PROVIDER: {provider}")


def _active_challenge(user, money_request_id: int):
    now = timezone.now()
    return (
        ApprovalSmsChallenge.objects.filter(
            user=user,
            money_request_id=money_request_id,
            consumed_at__isnull=True,
            expires_at__gte=now,
        )
        .order_by("-created_at")
        .first()
    )


def send_approval_sms_otp(
    user,
    money_request_id: int,
    *,
    force: bool = False,
    money_request=None,
) -> dict:
    if not approval_sms_otp_enabled():
        raise DarajaError("SMS approval codes are not enabled.")
    if not user_requires_stk_on_approval(user):
        raise DarajaError("PIN-on-approve is not enabled for your account.")

    phone = (user.phone or "").strip()
    if not phone:
        raise DarajaError("Add your phone number on Profile before approving with SMS.")

    msisdn = kenya_msisdn(phone)
    if not force:
        existing = _active_challenge(user, money_request_id)
        if existing:
            remaining = int((existing.expires_at - timezone.now()).total_seconds())
            return {
                "masked_phone": mask_phone(existing.phone),
                "expires_in_seconds": max(remaining, 0),
                "already_sent": True,
            }

    window_start = timezone.now() - SEND_WINDOW
    recent = ApprovalSmsChallenge.objects.filter(
        user=user,
        created_at__gte=window_start,
    ).count()
    if recent >= MAX_SENDS_PER_WINDOW:
        raise DarajaError("Too many codes sent. Wait a few minutes and try again.")

    ApprovalSmsChallenge.objects.filter(
        user=user,
        money_request_id=money_request_id,
        consumed_at__isnull=True,
    ).update(consumed_at=timezone.now())

    code = f"{secrets.randbelow(1_000_000):06d}"
    ttl = _otp_ttl()
    expires = timezone.now() + ttl
    ApprovalSmsChallenge.objects.create(
        user=user,
        money_request_id=money_request_id,
        phone=msisdn,
        code_hash=make_password(code),
        expires_at=expires,
    )

    product = getattr(django_settings, "PRODUCT_SMS_NAME", "NEXUS")
    amount_bit = ""
    if money_request is not None:
        amount_bit = f" KES {money_request.amount:,.2f}"
    message = (
        f"{product}{amount_bit} approval code: {code}. Valid {int(ttl.total_seconds() // 60)} min. "
        "Open NEXUS and enter this code to approve and send. Do not share."
    )
    _send_sms_message(to_msisdn=msisdn, message=message)

    return {
        "masked_phone": mask_phone(msisdn),
        "expires_in_seconds": int(ttl.total_seconds()),
        "already_sent": False,
    }


def send_approval_sms_on_notify(user, money_request) -> bool:
    """Text a one-time approval code when a money-request notification is created."""
    if not approval_sms_otp_enabled() or not user_requires_stk_on_approval(user):
        return False
    if not (user.phone or "").strip():
        logger.info(
            "Skipping approval SMS for user %s (no phone) on money request %s",
            user.pk,
            money_request.pk,
        )
        return False
    try:
        send_approval_sms_otp(user, money_request.pk, money_request=money_request)
        return True
    except DarajaError as exc:
        logger.warning(
            "Approval SMS on notify failed for user %s money request %s: %s",
            user.pk,
            money_request.pk,
            exc,
        )
        return False


def verify_approval_sms_otp(user, money_request_id: int, raw_code: str) -> bool:
    code = (raw_code or "").strip()
    if not code.isdigit() or len(code) != 6:
        return False
    now = timezone.now()
    challenge = (
        ApprovalSmsChallenge.objects.filter(
            user=user,
            money_request_id=money_request_id,
            consumed_at__isnull=True,
            expires_at__gte=now,
        )
        .order_by("-created_at")
        .first()
    )
    if not challenge:
        return False
    if not check_password(code, challenge.code_hash):
        return False
    challenge.consumed_at = now
    challenge.save(update_fields=["consumed_at"])
    return True

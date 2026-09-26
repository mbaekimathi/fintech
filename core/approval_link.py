"""Signed links so reviewers can approve with hub password without a login session."""

from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings as django_settings
from django.core import signing
from django.utils import timezone

from core.approval import user_requires_stk_on_approval, user_requires_app_on_approval
from core.models import ApprovalGuestToken

logger = logging.getLogger(__name__)

SIGN_SALT = "nexus-guest-approval-v1"


def guest_approval_enabled() -> bool:
    return bool(getattr(django_settings, "APPROVAL_GUEST_LINK", True))


def _link_ttl() -> timedelta:
    hours = getattr(django_settings, "APPROVAL_GUEST_LINK_TTL_HOURS", 48)
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        hours = 48
    return timedelta(hours=max(1, min(hours, 168)))


def reviewer_can_guest_approve(user) -> bool:
    if not user or not getattr(user, "is_authenticated", True):
        if user is None:
            return False
    if not user.is_active or not user.is_approved:
        return False
    if not user.can_review_requests():
        return False
    return user_requires_app_on_approval(user) or user_requires_stk_on_approval(user)


def issue_guest_approval_token(user, money_request_id: int) -> ApprovalGuestToken:
    now = timezone.now()
    ApprovalGuestToken.objects.filter(
        user=user,
        money_request_id=money_request_id,
        consumed_at__isnull=True,
    ).update(consumed_at=now)
    return ApprovalGuestToken.objects.create(
        user=user,
        money_request_id=money_request_id,
        expires_at=now + _link_ttl(),
    )


def sign_guest_token(row: ApprovalGuestToken) -> str:
    payload = f"{row.pk}:{row.user_id}:{row.money_request_id}"
    return signing.dumps(payload, salt=SIGN_SALT)


def resolve_guest_token(token: str) -> ApprovalGuestToken:
    try:
        raw = signing.loads(token, salt=SIGN_SALT, max_age=int(_link_ttl().total_seconds()))
    except signing.BadSignature as exc:
        raise ValueError("This approval link is invalid or has expired.") from exc
    parts = str(raw).split(":")
    if len(parts) != 3:
        raise ValueError("This approval link is invalid.")
    pk_s, user_id_s, mr_id_s = parts
    if not pk_s.isdigit() or not user_id_s.isdigit() or not mr_id_s.isdigit():
        raise ValueError("This approval link is invalid.")
    row = (
        ApprovalGuestToken.objects.filter(pk=int(pk_s))
        .select_related("user")
        .first()
    )
    if not row or row.user_id != int(user_id_s) or row.money_request_id != int(mr_id_s):
        raise ValueError("This approval link is invalid.")
    if row.consumed_at is not None:
        raise ValueError("This approval link was already used.")
    if row.expires_at < timezone.now():
        raise ValueError("This approval link has expired.")
    if not reviewer_can_guest_approve(row.user):
        raise ValueError("You are not allowed to approve payments with this link.")
    return row


def guest_approval_public_url(signed_token: str) -> str:
    base = (getattr(django_settings, "DARAJA_PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    path = f"/approve/guest/{signed_token}/"
    return f"{base}{path}" if base else path


def mint_guest_approval_link(user, money_request_id: int) -> tuple[str, str] | None:
    """Return (site_path, full_https_url) or None if guest links are off."""
    if not guest_approval_enabled() or not reviewer_can_guest_approve(user):
        return None
    row = issue_guest_approval_token(user, money_request_id)
    signed = sign_guest_token(row)
    path = f"/approve/guest/{signed}/"
    return path, guest_approval_public_url(signed)


def guest_approval_path_for(user, money_request_id: int) -> str:
    links = mint_guest_approval_link(user, money_request_id)
    return links[0] if links else "/paybill/transactions/"


def maybe_sms_guest_approval_link(user, money_request, full_url: str) -> None:
    if not full_url or not (user.phone or "").strip():
        return
    if not getattr(django_settings, "APPROVAL_GUEST_LINK_SMS", True):
        return
    try:
        from core.approval_sms import _send_sms_message
        from integrations.daraja_client import DarajaError, kenya_msisdn

        product = getattr(django_settings, "PRODUCT_SMS_NAME", "NEXUS")
        message = (
            f"{product}: Payment needs your approval. Open this link (no login): {full_url} "
            "Enter your hub approval password to approve and send."
        )
        _send_sms_message(to_msisdn=kenya_msisdn(user.phone), message=message)
    except Exception as exc:
        logger.warning("Guest approval SMS failed for user %s: %s", user.pk, exc)


def request_proxy_for_user(user, post_data):
    """Minimal request stand-in for approval + payout helpers."""
    return SimpleNamespace(user=user, POST=post_data, META={})

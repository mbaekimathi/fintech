"""Orchestrates app PIN and M-Pesa STK checks before a payout is approved."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages

from paybill.models import MoneyRequest

from core.approval import (
    approval_phone_stk_enabled,
    user_requires_app_on_approval,
    user_requires_stk_on_approval,
    verify_approval_pin,
    verify_stk_approval,
)
from core.approval_sms import approval_sms_otp_enabled, verify_approval_sms_otp


@dataclass(frozen=True)
class ApprovalChannels:
    """Which verification channels apply to this reviewer."""

    app: bool
    stk: bool

    @property
    def any(self) -> bool:
        return self.app or self.stk

    @property
    def both(self) -> bool:
        return self.app and self.stk


def channels_for(user) -> ApprovalChannels:
    return ApprovalChannels(
        app=user_requires_app_on_approval(user),
        stk=user_requires_stk_on_approval(user),
    )


def _sms_otp_verified(request, money_request: MoneyRequest) -> bool:
    if not approval_sms_otp_enabled() or not user_requires_stk_on_approval(request.user):
        return False
    pin = (request.POST.get("approval_pin") or request.POST.get("approval_sms_code") or "").strip()
    return verify_approval_sms_otp(request.user, money_request.pk, pin)


def _stk_verified_on_request(request, money_request: MoneyRequest) -> bool:
    raw_id = (request.POST.get("stk_approval_operation_id") or "").strip()
    if not raw_id.isdigit():
        return False
    return verify_stk_approval(request.user, int(raw_id), money_request)


def _app_pin_verified(request) -> bool:
    user = request.user
    pin = (request.POST.get("approval_pin") or "").strip()
    return bool(user.has_approval_password and verify_approval_pin(user, pin))


def _dual_channel_ok(request, money_request: MoneyRequest) -> bool:
    """When both channels are required, either a valid app PIN or a successful STK suffices."""
    user = request.user
    pin_ok = _app_pin_verified(request)
    stk_ok = _stk_verified_on_request(request, money_request)
    sms_ok = _sms_otp_verified(request, money_request)
    if pin_ok or stk_ok or sms_ok:
        return True

    if not user.has_approval_password and not (user.phone or "").strip():
        messages.error(
            request,
            "Set your approval password and phone number on Profile before approving payments.",
        )
        return False

    if (request.POST.get("approval_pin") or "").strip():
        messages.error(request, "Enter your 6-digit approval password to approve this payment.")
    elif not (user.phone or "").strip():
        messages.error(
            request,
            "Add your phone number on Profile, or enter your approval password in the app.",
        )
    else:
        if approval_sms_otp_enabled() and user_requires_stk_on_approval(user):
            messages.error(
                request,
                "Enter the 6-digit code we sent to your phone, or use your approval password in the app.",
            )
        else:
            messages.error(
                request,
                "Enter your approval password in the app or complete the M-Pesa PIN prompt on your phone.",
            )
    return False


def _app_only_ok(request) -> bool:
    user = request.user
    if not user.has_approval_password:
        messages.error(
            request,
            "Set your approval password on Profile before approving payments.",
        )
        return False
    if _app_pin_verified(request):
        return True
    messages.error(request, "Enter your 6-digit approval password to approve this payment.")
    return False


def _stk_only_ok(request, money_request: MoneyRequest) -> bool:
    if approval_phone_stk_enabled():
        if not (request.user.phone or "").strip():
            messages.error(request, "Add your phone number on Profile before PIN approval.")
            return False
        if _stk_verified_on_request(request, money_request):
            return True
        messages.error(request, "Complete the M-Pesa PIN prompt on your phone to approve this payment.")
        return False
    if not (request.user.phone or "").strip():
        messages.error(request, "Add your phone number on Profile before approving payments.")
        return False
    if approval_sms_otp_enabled():
        if _sms_otp_verified(request, money_request):
            return True
        if _app_pin_verified(request):
            return True
        messages.error(
            request,
            "Enter the 6-digit code we sent to your phone, or your approval password if you have one set.",
        )
        return False
    return _app_only_ok(request)


def authorize_payout_approval(
    request,
    *,
    money_request: MoneyRequest,
    next_url: str = "",
) -> bool:
    """
    Return True when the reviewer has satisfied the configured approval gate.

    Single channel: that channel must pass.
    Dual channel: app PIN **or** successful STK verification is enough to release the transfer.
    """
    _ = next_url  # kept for call-site compatibility with review views
    user = request.user
    ch = channels_for(user)
    if not ch.any:
        return True
    if ch.both:
        return _dual_channel_ok(request, money_request)
    if ch.app:
        return _app_only_ok(request)
    return _stk_only_ok(request, money_request)

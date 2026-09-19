"""Payment approval helpers."""

from __future__ import annotations

from django.contrib import messages

from core.models import AppSettings


def pin_approval_required() -> bool:
    return AppSettings.load().pin_approval_required


def verify_approval_pin(user, raw_pin: str) -> bool:
    pin = (raw_pin or "").strip()
    if not pin.isdigit() or len(pin) != 6:
        return False
    return user.check_password(pin)


def user_requires_pin_on_approval(user) -> bool:
    return user.requires_pin_on_approval()


def approval_pin_ok(request, *, next_url: str) -> bool:
    """Return True when approval may proceed (PIN verified or not required)."""
    if not user_requires_pin_on_approval(request.user):
        return True
    if verify_approval_pin(request.user, request.POST.get("approval_pin", "")):
        return True
    messages.error(request, "Enter your 6-digit password to approve this payment.")
    return False

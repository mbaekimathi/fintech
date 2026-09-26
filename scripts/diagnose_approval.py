#!/usr/bin/env python
"""Diagnose approval UI and backend gate on the current database."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from core.approval import approval_phone_stk_enabled
from core.approval_sms import approval_sms_otp_enabled
from core.models import AppSettings, Notification
from integrations.models import DarajaConfig
from paybill.models import MoneyRequest

UserModel = get_user_model()


def main() -> int:
    print("ASSET_VERSION:", settings.ASSET_VERSION)
    it = UserModel.objects.filter(role=User.Role.IT_SUPPORT, is_approved=True).first()
    if not it:
        print("No IT support user in database.")
        return 1

    app_settings = AppSettings.load()
    print(
        "Hub approval:",
        "app=", app_settings.app_approval_required,
        "stk=", app_settings.stk_pin_approval_required,
    )
    print(
        "Env STK:",
        "APPROVAL_STK_LIPA_CHARGE=", getattr(settings, "APPROVAL_STK_LIPA_CHARGE", False),
        "| APPROVAL_STK_PHONE_PROMPT=", getattr(settings, "APPROVAL_STK_PHONE_PROMPT", True),
        "| phone_stk_enabled=", approval_phone_stk_enabled(),
        "| sms_otp=", approval_sms_otp_enabled(),
        "| SMS_PROVIDER=", getattr(settings, "SMS_PROVIDER", ""),
    )
    daraja = DarajaConfig.load()
    print("Daraja STK ready:", daraja.stk_ready)
    perms = getattr(it, "permissions", None)
    if perms:
        print(
            "Employee perms:",
            "review=", perms.review_requests,
            "pin_on_approve=", perms.pin_approval_prompt,
            "stk_on_approve=", perms.stk_pin_approval_prompt,
        )
    print(
        "Reviewer gates:",
        "requires_app=", it.requires_app_on_approval(),
        "requires_stk=", it.requires_stk_on_approval(),
        "has_password=", it.has_approval_password,
        "phone=", it.phone or "(empty)",
    )
    if it.requires_stk_on_approval() and approval_phone_stk_enabled() and not it.phone:
        print("BLOCKER: PIN-on-approve STK needs a phone number on Profile.")
    if it.requires_stk_on_approval() and approval_phone_stk_enabled() and not daraja.stk_ready:
        print("BLOCKER: Daraja STK is not ready — finish STK setup in Daraja settings.")
    if it.requires_stk_on_approval() and approval_sms_otp_enabled():
        print("PIN-on-approve uses SMS one-time codes to the profile phone (not M-Pesa pay STK).")
    elif it.requires_stk_on_approval() and not approval_phone_stk_enabled():
        print("NOTE: Phone STK/SMS off; PIN-on-approve uses app approval password only.")

    pending = MoneyRequest.objects.filter(status=MoneyRequest.Status.PENDING).count()
    notes = Notification.objects.filter(
        recipient=it,
        kind=Notification.Kind.MONEY_REQUEST,
    ).count()
    print("Pending requests:", pending, "| reviewer notifications:", notes)

    client = Client()
    client.force_login(it)
    token = set_current_role_slug(role_to_slug(User.Role.IT_SUPPORT))
    try:
        page = client.get(reverse("core:dashboard"))
        html = page.content.decode()
        asset = re.search(r"app\.js\?v=([^\"']+)", html)
        print("Dashboard status:", page.status_code, "| app.js version:", asset.group(1) if asset else "missing")
        print("Has pin backdrop:", "data-pin-approval-backdrop" in html)
        print("Has approval trigger:", "data-approval-trigger" in html)
        match = re.search(r'id="approval-config">\s*(\{.*?\})\s*</script>', html, re.DOTALL)
        if not match:
            print("approval-config block: MISSING")
            return 1
        raw = match.group(1)
        print("approval-config contains .replace:", ".replace" in raw)
        try:
            config = json.loads(raw)
        except json.JSONDecodeError as exc:
            print("approval-config JSON: INVALID ->", exc)
            print(raw[:400])
            return 1
        print("approval-config JSON: OK")
        print("  stkPollUrl:", config.get("stkPollUrl"))
        print("  pendingPollUrl:", config.get("pendingPollUrl"))
        return 0
    finally:
        reset_current_role_slug(token)


if __name__ == "__main__":
    raise SystemExit(main())

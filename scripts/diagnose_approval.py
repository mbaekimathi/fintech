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
from core.models import AppSettings, Notification
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
        "Reviewer gates:",
        "requires_app=", it.requires_app_on_approval(),
        "requires_stk=", it.requires_stk_on_approval(),
        "has_password=", it.has_approval_password,
        "phone=", it.phone or "(empty)",
    )

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

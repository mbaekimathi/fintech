#!/usr/bin/env python
"""Quick sanity check for approval UI markup and server gate."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from core.models import AppSettings, Notification
from paybill.models import MoneyRequest, PaybillAccount

UserModel = get_user_model()


def main() -> int:
    paybill = PaybillAccount.objects.filter(is_active=True).first()
    it = UserModel.objects.filter(role=User.Role.IT_SUPPORT, is_approved=True).first()
    emp = UserModel.objects.filter(role=User.Role.EMPLOYEE, is_approved=True).first()
    if not paybill or not it or not emp:
        print("Missing fixtures (paybill, it support, or employee).")
        return 1

    settings = AppSettings.load()
    settings.app_approval_required = True
    settings.stk_pin_approval_required = False
    settings.save(update_fields=["app_approval_required", "stk_pin_approval_required"])
    it.set_approval_password("778899")
    it.save(update_fields=["approval_password"])

    req = MoneyRequest.objects.create(
        requester=emp,
        source_paybill=paybill,
        category=MoneyRequest.Category.TRAVEL,
        destination_type=MoneyRequest.DestinationType.PHONE,
        destination="0712345678",
        amount=Decimal("100.00"),
        reason="Approval check",
        status=MoneyRequest.Status.PENDING,
    )
    note = Notification.objects.create(
        recipient=it,
        actor=emp,
        kind=Notification.Kind.MONEY_REQUEST,
        title="Check requested KES 100.00",
        body="Phone number · 0712345678",
        money_request=req,
    )

    client = Client()
    client.force_login(it)
    token = set_current_role_slug(role_to_slug(User.Role.IT_SUPPORT))
    try:
        review_url = reverse("core:notification-review", kwargs={"pk": note.pk})
        page = client.get(reverse("core:dashboard"))
        html = page.content.decode()
        checks = {
            "pin_backdrop": "data-pin-approval-backdrop" in html,
            "approval_config": "approval-config" in html,
            "hub_app_true": '"hubApp": true' in html,
            "approval_trigger": "data-approval-trigger" in html,
            "app_js": "app.js" in html,
        }
        print("Page checks:", checks)
        if not all(checks.values()):
            return 1

        blocked = client.post(review_url, {"intent": "approve", "next": "/"})
        req.refresh_from_db()
        print(f"Approve without PIN: HTTP {blocked.status_code}, request={req.status}")
        if req.status != MoneyRequest.Status.PENDING:
            print("Expected request to stay pending without approval PIN.")
            return 1

        print("OK: approval UI present and server blocks missing PIN.")
        return 0
    finally:
        reset_current_role_slug(token)


if __name__ == "__main__":
    raise SystemExit(main())

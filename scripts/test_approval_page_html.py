#!/usr/bin/env python
"""Inspect transactions page approval wiring (HTML + JSON config)."""
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

from django.test import Client
from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from django.urls import reverse


def inspect(user: User, label: str) -> int:
    client = Client()
    client.force_login(user)
    token = set_current_role_slug(role_to_slug(user.role))
    try:
        url = reverse("paybill:transactions")
        r = client.get(url)
        html = r.content.decode()
        print(f"\n=== {label} ({user.staff_code}) status={r.status_code} ===")
        print("approval-config present:", "approval-config" in html)
        print("data-approval-form:", "data-approval-form" in html)
        print("data-approval-trigger:", "data-approval-trigger" in html)
        print("pin backdrop:", "data-pin-approval-backdrop" in html)
        print("stk backdrop:", "data-stk-approval-backdrop" in html)
        print("app.js linked:", "static/js/app.js" in html or "/static/js/app.js" in html)
        m = re.search(r'id="approval-config">\s*(\{.*?\})\s*</script>', html, re.DOTALL)
        if m:
            cfg = json.loads(m.group(1))
            print("config.app", cfg.get("app"), "config.stk", cfg.get("stk"))
            print("hubApp", cfg.get("hubApp"), "hubStk", cfg.get("hubStk"))
            print("stkInitiateUrl", cfg.get("stkInitiateUrl"))
            print("hasApprovalPassword", cfg.get("hasApprovalPassword"))
            print("hasPhone", cfg.get("hasPhone"))
        else:
            print("NO approval-config JSON")
        btn = re.search(
            r"data-approval-form[\s\S]{0,800}?Approve &amp; send",
            html,
        )
        if btn:
            snippet = btn.group(0)
            print("approve button type=", "type=\"button\"" in snippet)
            print("approve has trigger=", "data-approval-trigger" in snippet)
        return 0
    finally:
        reset_current_role_slug(token)


def main() -> int:
    for u in User.objects.filter(is_approved=True, is_active=True).order_by("staff_code")[:8]:
        if u.can_review_requests():
            inspect(u, u.get_role_display())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

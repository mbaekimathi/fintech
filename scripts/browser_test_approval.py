#!/usr/bin/env python
"""Browser test: Approve & send must open STK or PIN dialog."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from accounts.models import User
from accounts.role_urls import role_to_slug, workspace_url

UserModel = get_user_model()
BASE = os.environ.get("APPROVAL_TEST_BASE", "http://127.0.0.1:8765")


def main() -> int:
    from django.conf import settings
    from django.test import Client
    from playwright.sync_api import sync_playwright

    admin = UserModel.objects.filter(staff_code="100001", is_approved=True).first()
    if not admin:
        print("No admin user 100001")
        return 1

    path = workspace_url("/paybill/transactions/", User.Role.ADMIN)
    url = BASE.rstrip("/") + path

    session = Client()
    session.force_login(admin)
    cookie = session.cookies.get(settings.SESSION_COOKIE_NAME)
    if not cookie:
        print("Could not create session cookie")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": cookie.value,
                    "domain": "127.0.0.1",
                    "path": "/",
                }
            ]
        )
        context.set_default_timeout(15000)
        page = context.new_page()

        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("[data-pending-requests-tbody]", timeout=20000)

        ready = page.evaluate("() => Boolean(window.nexusApproval && window.nexusApproval.ready)")
        flow_ready = page.evaluate("() => Boolean(window.__approvalFlowReady)")
        print("nexusApproval.ready:", ready)
        print("approvalFlowReady:", flow_ready)

        btn = page.locator(
            "[data-pending-requests-tbody] form[data-approval-form] button[data-approval-trigger]"
        ).first
        if btn.count() == 0:
            print("No approve button found")
            browser.close()
            return 1

        dialogs_before = page.evaluate(
            """() => ({
              pinHidden: document.querySelector('[data-pin-approval-backdrop]')?.hidden,
              stkHidden: document.querySelector('[data-stk-approval-backdrop]')?.hidden,
            })"""
        )
        print("before click:", dialogs_before)

        page.once("dialog", lambda d: print("ALERT:", d.message) or d.accept())
        btn.click()

        page.wait_for_timeout(2500)

        dialogs_after = page.evaluate(
            """() => ({
              pinHidden: document.querySelector('[data-pin-approval-backdrop]')?.hidden,
              stkHidden: document.querySelector('[data-stk-approval-backdrop]')?.hidden,
              stkStatus: document.querySelector('[data-stk-approval-status]')?.textContent?.trim(),
              stkError: document.querySelector('[data-stk-approval-error]')?.textContent?.trim(),
            })"""
        )
        print("after click:", dialogs_after)

        ok = dialogs_after.get("pinHidden") is False or dialogs_after.get("stkHidden") is False
        if not ok and dialogs_after.get("stkError"):
            print("STK error:", dialogs_after.get("stkError"))
        if not ok:
            print("FAIL: no dialog visible after click")
            browser.close()
            return 1

        print("OK: approval UI reacted to click")
        browser.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

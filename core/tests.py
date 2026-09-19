import json
import re
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import EmployeePermissions, User
from accounts.permissions import sync_permissions_from_role
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from core.approval import approval_stk_account_ref
from core.models import AppSettings, Notification, PushSubscription
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import MoneyRequest, PaybillAccount

UserModel = get_user_model()


class NotificationFlowTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888111",
            account_name="Hub Paybill",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="400001",
            password="test-pass-123",
            email="employee.notify@example.com",
            first_name="Emp",
            last_name="Loyee",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.it_support = UserModel.objects.create_user(
            staff_code="400002",
            password="test-pass-123",
            email="it.notify@example.com",
            first_name="IT",
            last_name="Support",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )
        config = DarajaConfig.load()
        config.environment = DarajaConfig.Environment.SANDBOX
        config.paybill_account = self.paybill
        config.shortcode = "174379"
        config.org_shortcode = "600996"
        config.initiator_name = "testapi"
        config.security_credential = "Safaricom123!!"
        config.consumer_key = "key"
        config.consumer_secret = "secret"
        config.passkey = "pass"
        config.stk_callback_url = "https://example.test/api/v1/daraja/stk/callback/"
        config.result_url = "https://example.test/api/v1/daraja/result/"
        config.timeout_url = "https://example.test/api/v1/daraja/timeout/"
        config.b2c_enabled = True
        config.b2c_command_id = DarajaConfig.B2CCommand.BUSINESS
        config.save()

    def _url(self, role: str, name: str, **kwargs) -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name, kwargs=kwargs or None)
        finally:
            reset_current_role_slug(token)

    def test_employee_request_notifies_reviewers(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            self._url(User.Role.EMPLOYEE, "core:dashboard"),
            {
                "category": MoneyRequest.Category.TRAVEL,
                "destination_type": MoneyRequest.DestinationType.PHONE,
                "destination": "0712345678",
                "account_ref": "",
                "amount": "750.00",
                "reason": "Field visit fuel",
            },
        )
        self.assertEqual(response.status_code, 302)
        note = Notification.objects.get(recipient=self.it_support)
        self.assertEqual(note.kind, Notification.Kind.MONEY_REQUEST)
        self.assertIn("750.00", note.title)
        self.assertFalse(note.is_read)

        self.client.force_login(self.it_support)
        page = self.client.get(self._url(User.Role.IT_SUPPORT, "core:dashboard"))
        self.assertContains(page, "Notifications")
        self.assertContains(page, "Approve &amp; send")
        self.assertContains(page, "0712345678")

    def test_employee_can_reprompt_pending_request(self):
        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        old_note = Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Loyee requested KES 750.00",
            body="Phone number · 0712345678",
            money_request=req,
            is_read=True,
        )
        self.client.force_login(self.employee)
        response = self.client.post(
            self._url(User.Role.EMPLOYEE, "core:dashboard"),
            {"intent": "reprompt", "money_request_id": str(req.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Notification.objects.filter(pk=old_note.pk).exists())
        new_note = Notification.objects.get(
            recipient=self.it_support,
            money_request=req,
            kind=Notification.Kind.MONEY_REQUEST,
        )
        self.assertFalse(new_note.is_read)
        self.assertIn("750.00", new_note.title)

    def test_employee_cannot_reprompt_another_users_request(self):
        other = UserModel.objects.create_user(
            staff_code="400003",
            password="test-pass-123",
            email="other.reprompt@example.com",
            first_name="Other",
            last_name="Emp",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        req = MoneyRequest.objects.create(
            requester=other,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        self.client.force_login(self.employee)
        response = self.client.post(
            self._url(User.Role.EMPLOYEE, "core:dashboard"),
            {"intent": "reprompt", "money_request_id": str(req.pk)},
        )
        self.assertEqual(response.status_code, 404)

    def test_reject_from_notification_updates_employee(self):
        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        note = Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Loyee requested KES 750.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk),
            {"intent": "reject", "next": "/"},
        )
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        note.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.REJECTED)
        self.assertTrue(note.is_read)
        employee_note = Notification.objects.get(
            recipient=self.employee,
            kind=Notification.Kind.MONEY_REQUEST_RESULT,
        )
        self.assertIn("rejected", employee_note.title.lower())

    def test_header_shows_only_session_user_notifications(self):
        other = UserModel.objects.create_user(
            staff_code="400099",
            password="test-pass-123",
            email="other.notify@example.com",
            first_name="Other",
            last_name="Emp",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        mine = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("100.00"),
            reason="Mine",
            status=MoneyRequest.Status.PAID,
        )
        theirs = MoneyRequest.objects.create(
            requester=other,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.MEALS,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0799999999",
            amount=Decimal("200.00"),
            reason="Theirs",
            status=MoneyRequest.Status.PAID,
        )
        Notification.objects.create(
            recipient=self.employee,
            kind=Notification.Kind.MONEY_REQUEST_RESULT,
            title="Request paid: KES 100.00",
            body="Phone number · 0712345678",
            money_request=mine,
        )
        Notification.objects.create(
            recipient=other,
            kind=Notification.Kind.MONEY_REQUEST_RESULT,
            title="Request paid: KES 200.00",
            body="Phone number · 0799999999",
            money_request=theirs,
        )
        # Review-queue copy must not appear for an employee session.
        Notification.objects.create(
            recipient=self.employee,
            actor=other,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Other Emp requested KES 200.00",
            body="Phone number · 0799999999",
            money_request=theirs,
        )

        self.client.force_login(self.employee)
        page = self.client.get(self._url(User.Role.EMPLOYEE, "core:dashboard"))
        self.assertContains(page, "Request paid: KES 100.00")
        self.assertNotContains(page, "Request paid: KES 200.00")
        self.assertNotContains(page, "Other Emp requested")

    def test_role_switch_hides_review_queue_for_employee_view(self):
        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Loyee requested KES 750.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        self.client.force_login(self.it_support)
        as_it = self.client.get(self._url(User.Role.IT_SUPPORT, "core:dashboard"))
        self.assertContains(as_it, "Emp Loyee requested KES 750.00")

        session = self.client.session
        session["view_as_role"] = User.Role.EMPLOYEE
        session.save()
        as_employee = self.client.get(self._url(User.Role.EMPLOYEE, "core:dashboard"))
        self.assertNotContains(as_employee, "Emp Loyee requested KES 750.00")

    def test_approve_from_notification_triggers_transfer(self):
        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        note = Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Loyee requested KES 750.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_NOTIFY_1",
            "OriginatorConversationID": "ORIG_NOTIFY_1",
        }
        self.client.force_login(self.it_support)
        with patch("integrations.daraja_client.DarajaClient.access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                response = self.client.post(
                    self._url(
                        User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk
                    ),
                    {"intent": "approve", "next": "/"},
                )
        self.assertRedirects(
            response,
            self._url(User.Role.IT_SUPPORT, "paybill:transactions"),
            fetch_redirect_response=False,
        )
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.APPROVED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.employee,
                kind=Notification.Kind.MONEY_REQUEST_RESULT,
            ).exists()
        )


class WebPushTests(TestCase):
    def setUp(self):
        self.it_support = UserModel.objects.create_user(
            staff_code="400012",
            password="test-pass-123",
            email="it.push@example.com",
            first_name="IT",
            last_name="Push",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="400011",
            password="test-pass-123",
            email="emp.push@example.com",
            first_name="Emp",
            last_name="Push",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888222",
            account_name="Hub",
            is_active=True,
        )

    def _url(self, role: str, name: str, **kwargs) -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name, kwargs=kwargs or None)
        finally:
            reset_current_role_slug(token)

    def test_service_worker_and_manifest_unprefixed(self):
        sw = self.client.get("/sw.js")
        self.assertEqual(sw.status_code, 200)
        self.assertIn("Service-Worker-Allowed", sw.headers)
        self.assertIn(b"push", sw.content)
        manifest = self.client.get("/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertIn("application/manifest+json", manifest["Content-Type"])
        self.assertEqual(manifest.json()["short_name"], "NEXUS")
        self.assertNotIn(b"<!DOCTYPE", manifest.content)

    def test_subscribe_saves_push_endpoint(self):
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:push-subscribe"),
            data='{"endpoint":"https://push.example/x","keys":{"p256dh":"abc","auth":"def"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        row = PushSubscription.objects.get(user=self.it_support)
        self.assertEqual(row.endpoint, "https://push.example/x")
        self.assertEqual(row.endpoint_hash, PushSubscription.hash_endpoint(row.endpoint))

    def test_subscribe_rebinds_endpoint_to_session_user(self):
        PushSubscription.objects.create(
            user=self.it_support,
            endpoint="https://push.example/shared",
            endpoint_hash=PushSubscription.hash_endpoint("https://push.example/shared"),
            p256dh="abc",
            auth="def",
        )
        self.client.force_login(self.employee)
        response = self.client.post(
            self._url(User.Role.EMPLOYEE, "core:push-subscribe"),
            data='{"endpoint":"https://push.example/shared","keys":{"p256dh":"abc","auth":"def"}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        row = PushSubscription.objects.get(endpoint="https://push.example/shared")
        self.assertEqual(row.user_id, self.employee.pk)
        self.assertFalse(PushSubscription.objects.filter(user=self.it_support).exists())

    def test_money_request_triggers_web_push(self):
        PushSubscription.objects.create(
            user=self.it_support,
            endpoint="https://push.example/y",
            endpoint_hash=PushSubscription.hash_endpoint("https://push.example/y"),
            p256dh="abc",
            auth="def",
        )
        req = MoneyRequest(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("100.00"),
            reason="Taxi",
            status=MoneyRequest.Status.PENDING,
        )
        req.save()
        with patch("core.notifications.send_web_push_to_user") as send_push:
            from core.notifications import notify_money_request_submitted

            notify_money_request_submitted(req)
            self.assertTrue(send_push.called)
            self.assertEqual(send_push.call_args.args[0], self.it_support)


class HubBalanceDashboardTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888111",
            account_name="Hub Paybill",
            is_active=True,
        )
        self.it_support = UserModel.objects.create_user(
            staff_code="400010",
            password="test-pass-123",
            email="it.balance@example.com",
            first_name="IT",
            last_name="Support",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="400011",
            password="test-pass-123",
            email="employee.balance@example.com",
            first_name="Emp",
            last_name="Loyee",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        config = DarajaConfig.load()
        config.environment = DarajaConfig.Environment.SANDBOX
        config.paybill_account = self.paybill
        config.shortcode = "174379"
        config.org_shortcode = "600996"
        config.initiator_name = "testapi"
        config.security_credential = "Safaricom123!!"
        config.consumer_key = "key"
        config.consumer_secret = "secret"
        config.passkey = "pass"
        config.b2b_enabled = True
        config.stk_callback_url = "https://example.test/api/v1/daraja/stk/callback/"
        config.result_url = "https://example.test/api/v1/daraja/result/"
        config.timeout_url = "https://example.test/api/v1/daraja/timeout/"
        config.save()

    def _url(self, role: str, name: str, **kwargs) -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name, kwargs=kwargs or None)
        finally:
            reset_current_role_slug(token)

    def test_it_support_dashboard_shows_simple_account_view(self):
        DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.BALANCE,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            summary="Working KES 346499.00 · Utility KES 12.50",
            created_by=self.it_support,
        )
        self.client.force_login(self.it_support)
        response = self.client.get(self._url(User.Role.IT_SUPPORT, "core:dashboard"))
        self.assertContains(response, "account-dashboard")
        self.assertContains(response, "balance-card")
        self.assertContains(response, "Hub Paybill")
        self.assertContains(response, "888111")
        self.assertContains(response, "Utility")
        self.assertContains(response, "Working")
        self.assertContains(response, "STK collections")
        self.assertContains(response, "Move to working")
        self.assertNotContains(response, "Latest postings")
        self.assertNotContains(response, "stat-grid")

    def test_employee_dashboard_hides_balance_panel(self):
        self.client.force_login(self.employee)
        response = self.client.get(self._url(User.Role.EMPLOYEE, "core:dashboard"))
        self.assertNotContains(response, "account-dashboard")
        self.assertNotContains(response, "Move to working")

    def test_hub_balance_poll_returns_json(self):
        DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.BALANCE,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            summary="Working KES 100.00 · Utility KES 12.50",
            created_by=self.it_support,
        )
        self.client.force_login(self.it_support)
        response = self.client.get(
            self._url(User.Role.IT_SUPPORT, "core:dashboard"),
            {"poll": "hub-balance"},
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(str(payload["utility_amount"]), "12.50")
        self.assertEqual(str(payload["working_amount"]), "100.00")
        self.assertEqual(payload["paybill_number"], "888111")

    @patch("core.views.request_hub_balance")
    def test_hub_balance_refresh_reuses_pending_queue(self, mock_request):
        DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.BALANCE,
            status=DarajaOperation.Status.QUEUED,
            destination="600996",
            summary="Balance requested. Waiting for Daraja result.",
            created_by=self.it_support,
        )
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:dashboard"),
            {"intent": "hub-balance"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["watch"])
        mock_request.assert_not_called()

    @patch("core.views.request_hub_balance")
    def test_hub_balance_refresh_queues_request(self, mock_request):
        DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.BALANCE,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            summary="Working KES 100.00 · Utility KES 12.50",
            created_by=self.it_support,
        )

        def _queue_balance(**kwargs):
            return DarajaOperation.objects.create(
                kind=DarajaOperation.Kind.BALANCE,
                status=DarajaOperation.Status.QUEUED,
                destination="600996",
                summary="Balance requested. Waiting for Daraja result.",
                created_by=self.it_support,
            )

        mock_request.side_effect = _queue_balance
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:dashboard"),
            {"intent": "hub-balance"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["watch"])
        mock_request.assert_called_once()

    @patch("core.views.wait_for_result")
    @patch("integrations.daraja_client.DarajaClient.utility_to_working")
    def test_utility_transfer_posts_b2b_operation(self, mock_transfer, mock_wait):
        operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2B,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            amount=Decimal("10.00"),
            account_ref="UTILITY-WORKING",
            summary="Moved KES 10 to working capital.",
            created_by=self.it_support,
        )
        mock_transfer.return_value = (
            {"ResponseDescription": "Accepted"},
            {"CommandID": "BusinessTransferFromUtilityToMMF", "Amount": 10},
            "600996",
        )
        mock_wait.return_value = operation
        DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.BALANCE,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            summary="Working KES 100.00 · Utility KES 12.50",
            created_by=self.it_support,
        )
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:dashboard"),
            {"intent": "utility-transfer", "amount": "10"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transfer"]["amount"], "10")
        mock_transfer.assert_called_once()


class AppSettingsTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888222",
            account_name="Hub Paybill",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="500001",
            password="112233",
            email="employee.apps@example.com",
            first_name="Emp",
            last_name="Apps",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.it_support = UserModel.objects.create_user(
            staff_code="500002",
            password="445566",
            email="it.apps@example.com",
            first_name="IT",
            last_name="Apps",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )
        config = DarajaConfig.load()
        config.environment = DarajaConfig.Environment.SANDBOX
        config.paybill_account = self.paybill
        config.shortcode = "174379"
        config.org_shortcode = "600996"
        config.initiator_name = "testapi"
        config.security_credential = "Safaricom123!!"
        config.consumer_key = "key"
        config.consumer_secret = "secret"
        config.passkey = "pass"
        config.stk_callback_url = "https://example.test/api/v1/daraja/stk/callback/"
        config.result_url = "https://example.test/api/v1/daraja/result/"
        config.timeout_url = "https://example.test/api/v1/daraja/timeout/"
        config.b2c_enabled = True
        config.b2c_command_id = DarajaConfig.B2CCommand.BUSINESS
        config.save()
        AppSettings.load()

    def _url(self, role: str, name: str, **kwargs) -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name, kwargs=kwargs or None)
        finally:
            reset_current_role_slug(token)

    def test_app_settings_page_and_sidebar_link(self):
        self.client.force_login(self.it_support)
        settings_page = self.client.get(self._url(User.Role.IT_SUPPORT, "core:settings"))
        self.assertContains(settings_page, "App settings")
        app_page = self.client.get(self._url(User.Role.IT_SUPPORT, "core:app-settings"))
        self.assertContains(app_page, "App approval")
        self.assertContains(app_page, "PIN approval (STK push)")

    def test_toggle_app_approval_via_ajax(self):
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:app-settings"),
            {"app_approval_required": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["app_approval_required"])
        self.assertTrue(AppSettings.load().app_approval_required)

    def test_pending_approval_poll_returns_review_queue(self):
        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("250.00"),
            reason="Taxi",
            status=MoneyRequest.Status.PENDING,
        )
        Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Apps requested KES 250.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        self.client.force_login(self.it_support)
        response = self.client.get(
            self._url(User.Role.IT_SUPPORT, "core:approval-pending-poll"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["pending"]), 1)
        self.assertEqual(payload["pending"][0]["money_request_id"], req.pk)
        self.assertIn("notifications", payload)
        self.assertEqual(len(payload["notifications"]), 1)

    def test_toggle_stk_pin_approval_via_ajax(self):
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:app-settings"),
            {"stk_pin_approval_required": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stk_pin_approval_required"])
        self.assertTrue(AppSettings.load().stk_pin_approval_required)

    def _enable_pin_prompt(self, user, *, approval_password: str = "778899"):
        sync_permissions_from_role(user, reset=True)
        perms = EmployeePermissions.objects.get(user=user)
        perms.pin_approval_prompt = True
        perms.save(update_fields=["pin_approval_prompt", "updated_at"])
        user.set_approval_password(approval_password)
        user.save(update_fields=["approval_password"])

    def _enable_both_approval_prompts(self, user, *, approval_password: str = "778899"):
        sync_permissions_from_role(user, reset=True)
        perms = EmployeePermissions.objects.get(user=user)
        perms.pin_approval_prompt = True
        perms.stk_pin_approval_prompt = True
        perms.save(
            update_fields=["pin_approval_prompt", "stk_pin_approval_prompt", "updated_at"]
        )
        user.set_approval_password(approval_password)
        user.phone = "0712345678"
        user.save(update_fields=["approval_password", "phone"])

    def test_approve_requires_pin_when_enabled(self):
        settings = AppSettings.load()
        settings.app_approval_required = True
        settings.save(update_fields=["app_approval_required"])
        self._enable_pin_prompt(self.it_support)

        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("500.00"),
            reason="Fuel",
            status=MoneyRequest.Status.PENDING,
        )
        note = Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Apps requested KES 500.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        self.client.force_login(self.it_support)

        blocked = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk),
            {"intent": "approve", "next": "/"},
        )
        self.assertEqual(blocked.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.PENDING)

        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_PIN_1",
            "OriginatorConversationID": "ORIG_PIN_1",
        }
        with patch("integrations.daraja_client.DarajaClient.access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                approved = self.client.post(
                    self._url(User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk),
                    {"intent": "approve", "approval_pin": "778899", "next": "/"},
                )
        self.assertRedirects(
            approved,
            self._url(User.Role.IT_SUPPORT, "paybill:transactions"),
            fetch_redirect_response=False,
        )
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.APPROVED)

    def test_approve_accepts_stk_without_app_pin_when_both_enabled(self):
        settings = AppSettings.load()
        settings.app_approval_required = True
        settings.stk_pin_approval_required = True
        settings.save(update_fields=["app_approval_required", "stk_pin_approval_required"])
        self._enable_both_approval_prompts(self.it_support)

        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("500.00"),
            reason="Fuel",
            status=MoneyRequest.Status.PENDING,
        )
        note = Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Apps requested KES 500.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        stk_op = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.STK,
            status=DarajaOperation.Status.SUCCESS,
            destination="254712345678",
            amount=Decimal("1.00"),
            account_ref=approval_stk_account_ref(req.pk),
            summary="PIN verified",
            created_by=self.it_support,
        )
        self.client.force_login(self.it_support)
        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_PIN_3",
            "OriginatorConversationID": "ORIG_PIN_3",
        }
        with patch("integrations.daraja_client.DarajaClient.access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                approved = self.client.post(
                    self._url(User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk),
                    {
                        "intent": "approve",
                        "stk_approval_operation_id": str(stk_op.pk),
                        "next": "/",
                    },
                )
        self.assertRedirects(
            approved,
            self._url(User.Role.IT_SUPPORT, "paybill:transactions"),
            fetch_redirect_response=False,
        )
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.APPROVED)

    def test_approve_requires_pin_when_hub_on_without_person_toggle(self):
        settings = AppSettings.load()
        settings.app_approval_required = True
        settings.save(update_fields=["app_approval_required"])
        sync_permissions_from_role(self.it_support, reset=True)
        perms = EmployeePermissions.objects.get(user=self.it_support)
        perms.pin_approval_prompt = False
        perms.save(update_fields=["pin_approval_prompt", "updated_at"])
        self.it_support.set_approval_password("778899")
        self.it_support.save(update_fields=["approval_password"])
        self.assertTrue(self.it_support.requires_app_on_approval())

        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("500.00"),
            reason="Fuel",
            status=MoneyRequest.Status.PENDING,
        )
        note = Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Apps requested KES 500.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        self.client.force_login(self.it_support)

        blocked = self.client.post(
            self._url(User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk),
            {"intent": "approve", "next": "/"},
        )
        self.assertEqual(blocked.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.PENDING)

        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_PIN_2",
            "OriginatorConversationID": "ORIG_PIN_2",
        }
        with patch("integrations.daraja_client.DarajaClient.access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                response = self.client.post(
                    self._url(User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk),
                    {"intent": "approve", "approval_pin": "778899", "next": "/"},
                )
        self.assertRedirects(
            response,
            self._url(User.Role.IT_SUPPORT, "paybill:transactions"),
            fetch_redirect_response=False,
        )
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.APPROVED)

    def test_reviewer_workspace_includes_pin_dialog_and_approval_config(self):
        settings = AppSettings.load()
        settings.app_approval_required = True
        settings.stk_pin_approval_required = True
        settings.save(update_fields=["app_approval_required", "stk_pin_approval_required"])
        self.it_support.set_approval_password("778899")
        self.it_support.save(update_fields=["approval_password"])

        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("250.00"),
            reason="Taxi",
            status=MoneyRequest.Status.PENDING,
        )
        Notification.objects.create(
            recipient=self.it_support,
            actor=self.employee,
            kind=Notification.Kind.MONEY_REQUEST,
            title="Emp Apps requested KES 250.00",
            body="Phone number · 0712345678",
            money_request=req,
        )
        self.client.force_login(self.it_support)
        page = self.client.get(self._url(User.Role.IT_SUPPORT, "core:dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-pin-approval-backdrop")
        self.assertContains(page, "data-pin-approval-input")
        self.assertContains(page, '"hubApp": true')
        self.assertContains(page, '"autoPrompt": true')
        self.assertContains(page, "data-approval-trigger")
        self.assertContains(page, f'data-money-request-id="{req.pk}"')

    def test_approval_config_json_is_valid(self):
        settings = AppSettings.load()
        settings.app_approval_required = True
        settings.stk_pin_approval_required = True
        settings.save(update_fields=["app_approval_required", "stk_pin_approval_required"])
        self.client.force_login(self.it_support)
        page = self.client.get(self._url(User.Role.IT_SUPPORT, "core:dashboard"))
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        match = re.search(r'id="approval-config">\s*(\{.*?\})\s*</script>', html, re.DOTALL)
        self.assertIsNotNone(match, "approval-config JSON block missing")
        config_text = match.group(1)
        self.assertNotIn(".replace", config_text)
        config = json.loads(config_text)
        self.assertTrue(config["hubApp"])
        self.assertTrue(config["hubStk"])
        self.assertTrue(config["stkPollUrl"].endswith("/"))
        self.assertIn("/approval/stk/", config["stkPollUrl"])
        self.assertIn("hasApprovalPassword", config)
        self.assertIn("hasPhone", config)
        self.assertIn("dualApproval", config)
        self.assertTrue(config["dualApproval"])
        self.assertIn("profileUrl", config)

    def test_dual_approval_transactions_ajax_returns_json_redirect(self):
        settings = AppSettings.load()
        settings.app_approval_required = True
        settings.stk_pin_approval_required = True
        settings.save(update_fields=["app_approval_required", "stk_pin_approval_required"])
        self._enable_both_approval_prompts(self.it_support)

        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("300.00"),
            reason="Supplies",
            status=MoneyRequest.Status.PENDING,
        )
        self.client.force_login(self.it_support)
        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_DUAL_1",
            "OriginatorConversationID": "ORIG_DUAL_1",
        }
        with patch("integrations.daraja_client.DarajaClient.access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                with patch("integrations.callbacks.wait_for_result") as wait:
                    def mark_success(operation, timeout=8.0, interval=0.3):
                        operation.status = DarajaOperation.Status.SUCCESS
                        operation.summary = "Sent KES 300"
                        operation.save(update_fields=["status", "summary", "updated_at"])
                        return operation

                    wait.side_effect = mark_success
                    response = self.client.post(
                        self._url(User.Role.IT_SUPPORT, "paybill:money-request-review", pk=req.pk),
                        {"intent": "approve", "approval_pin": "778899"},
                        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                    )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("/transactions/", payload["redirect"])
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.APPROVED)
        self.assertIsNotNone(req.daraja_operation_id)

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from core.models import Notification, PushSubscription
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
                with patch("paybill.services.wait_for_result") as wait:
                    def mark_success(operation, timeout=8.0, interval=0.3):
                        operation.status = DarajaOperation.Status.SUCCESS
                        operation.summary = "Sent KES 750"
                        operation.save(update_fields=["status", "summary", "updated_at"])
                        return operation

                    wait.side_effect = mark_success
                    response = self.client.post(
                        self._url(
                            User.Role.IT_SUPPORT, "core:notification-review", pk=note.pk
                        ),
                        {"intent": "approve", "next": "/"},
                    )
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.PAID)
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
        self.assertEqual(manifest.json()["short_name"], "NEXUS")

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

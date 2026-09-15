from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from paybill.models import MoneyRequest, PaybillAccount

UserModel = get_user_model()


class MoneyRequestDashboardTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888111",
            account_name="Hub Paybill",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="300001",
            password="test-pass-123",
            email="employee.money@example.com",
            first_name="Emp",
            last_name="Loyee",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.admin = UserModel.objects.create_user(
            staff_code="300002",
            password="test-pass-123",
            email="admin.money@example.com",
            first_name="Ad",
            last_name="Min",
            role=User.Role.ADMIN,
            is_approved=True,
        )

    def _dash(self, role: str) -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse("core:dashboard")
        finally:
            reset_current_role_slug(token)

    def test_employee_sees_request_form(self):
        self.client.force_login(self.employee)
        response = self.client.get(self._dash(User.Role.EMPLOYEE))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request money")
        self.assertContains(response, "Hub Paybill")
        self.assertContains(response, "Expense category")

    def test_employee_can_submit_phone_request(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            self._dash(User.Role.EMPLOYEE),
            {
                "category": MoneyRequest.Category.TRAVEL,
                "destination_type": MoneyRequest.DestinationType.PHONE,
                "destination": "0712345678",
                "account_ref": "",
                "amount": "750.00",
                "reason": "Field visit fuel",
            },
        )
        self.assertRedirects(
            response, self._dash(User.Role.EMPLOYEE), fetch_redirect_response=False
        )
        req = MoneyRequest.objects.get(requester=self.employee)
        self.assertEqual(req.source_paybill, self.paybill)
        self.assertEqual(req.destination, "0712345678")
        self.assertEqual(req.amount, Decimal("750.00"))
        self.assertEqual(req.status, MoneyRequest.Status.PENDING)

    def test_employee_sees_pending_and_approved_sections(self):
        from integrations.models import DarajaOperation

        MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            status=DarajaOperation.Status.SUCCESS,
            destination="254712345678",
            amount=Decimal("500.00"),
            summary="Sent KES 500.00 · QWE123XYZ",
            result_payload={
                "Result": {
                    "ResultParameters": {
                        "ResultParameter": [
                            {"Key": "TransactionReceipt", "Value": "QWE123XYZ"},
                        ]
                    }
                }
            },
        )
        MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.MEALS,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0711111111",
            amount=Decimal("500.00"),
            reason="Client lunch",
            status=MoneyRequest.Status.PAID,
            daraja_operation=operation,
        )
        self.client.force_login(self.employee)
        response = self.client.get(self._dash(User.Role.EMPLOYEE))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending requests")
        self.assertContains(response, "Approved requests")
        self.assertContains(response, "0712345678")
        self.assertContains(response, "0711111111")
        self.assertContains(response, "M-Pesa reference")
        self.assertContains(response, "QWE123XYZ")

    def test_paybill_requires_account_ref(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            self._dash(User.Role.EMPLOYEE),
            {
                "category": MoneyRequest.Category.UTILITIES,
                "destination_type": MoneyRequest.DestinationType.PAYBILL,
                "destination": "123456",
                "account_ref": "",
                "amount": "100",
                "reason": "Water bill payment",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter the account number for that paybill.")
        self.assertFalse(MoneyRequest.objects.exists())

    def test_admin_dashboard_unchanged(self):
        self.client.force_login(self.admin)
        response = self.client.get(self._dash(User.Role.ADMIN))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Request money")
        self.assertContains(response, "Latest")


class PendingTransactionsTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888111",
            account_name="Hub Paybill",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="300011",
            password="test-pass-123",
            email="employee.pending@example.com",
            first_name="Emp",
            last_name="Loyee",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.it_support = UserModel.objects.create_user(
            staff_code="300012",
            password="test-pass-123",
            email="it.pending@example.com",
            first_name="IT",
            last_name="Support",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )

    def _url(self, role: str, name: str = "paybill:transactions") -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name)
        finally:
            reset_current_role_slug(token)

    def test_employee_request_appears_in_it_pending_transactions(self):
        MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )
        self.client.force_login(self.it_support)
        response = self.client.get(self._url(User.Role.IT_SUPPORT))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending transactions")
        self.assertContains(response, "0712345678")
        self.assertContains(response, "750.00")
        self.assertContains(response, "Emp Loyee")
        self.assertContains(response, "300011")
        self.assertContains(response, "Travel")
        self.assertContains(response, "Field visit fuel")
        self.assertContains(response, "Initiator")
        self.assertContains(response, "Approve &amp; send")
        self.assertContains(response, "Reject")

    def test_entries_show_initiator_and_clickable_category(self):
        from paybill.models import LedgerEntry

        LedgerEntry.objects.create(
            reference="NX-INIT-001",
            paybill_account=self.paybill,
            amount=Decimal("750.00"),
            payer_name="Emp Loyee",
            status=LedgerEntry.Status.COMPLETED,
            raw_payload={
                "_money_request": {
                    "id": 1,
                    "category": MoneyRequest.Category.TRAVEL,
                    "category_label": "Travel",
                    "reason": "Field visit fuel",
                    "initiator": "Emp Loyee",
                    "initiator_code": "300011",
                }
            },
        )
        self.client.force_login(self.it_support)
        response = self.client.get(self._url(User.Role.IT_SUPPORT))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NX-INIT-001")
        self.assertContains(response, "Emp Loyee")
        self.assertContains(response, "300011")
        self.assertContains(response, "Travel")
        self.assertContains(response, "Field visit fuel")
        self.assertContains(response, "View transfer details")
        self.assertContains(response, "Transfer details")
        self.assertContains(response, "Reason for transfer")


class MoneyRequestReviewTests(TestCase):
    def setUp(self):
        from integrations.models import DarajaConfig

        self.paybill = PaybillAccount.objects.create(
            paybill_number="888111",
            account_name="Hub Paybill",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="300021",
            password="test-pass-123",
            email="employee.review@example.com",
            first_name="Emp",
            last_name="Loyee",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.it_support = UserModel.objects.create_user(
            staff_code="300022",
            password="test-pass-123",
            email="it.review@example.com",
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
        config.b2b_enabled = True
        config.save()

    def _url(self, role: str, name: str, **kwargs) -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name, kwargs=kwargs or None)
        finally:
            reset_current_role_slug(token)

    def _pending_phone_request(self) -> MoneyRequest:
        return MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("750.00"),
            reason="Field visit fuel",
            status=MoneyRequest.Status.PENDING,
        )

    def test_reject_pending_request(self):
        req = self._pending_phone_request()
        self.client.force_login(self.it_support)
        response = self.client.post(
            self._url(User.Role.IT_SUPPORT, "paybill:money-request-review", pk=req.pk),
            {"intent": "reject"},
        )
        self.assertRedirects(
            response,
            self._url(User.Role.IT_SUPPORT, "paybill:transactions"),
            fetch_redirect_response=False,
        )
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.REJECTED)
        self.assertEqual(req.reviewed_by, self.it_support)

    def test_approve_triggers_daraja_b2c(self):
        from unittest.mock import patch

        from integrations.models import DarajaOperation

        req = self._pending_phone_request()
        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_REVIEW_1",
            "OriginatorConversationID": "ORIG_REVIEW_1",
        }
        self.client.force_login(self.it_support)
        with patch("integrations.daraja_client.DarajaClient.access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                with patch("paybill.services.wait_for_result") as wait:
                    def mark_success(operation, timeout=8.0, interval=0.3):
                        operation.status = DarajaOperation.Status.SUCCESS
                        operation.summary = "Sent KES 750 · NHL61H8XYZ"
                        operation.mpesa_reference = "NHL61H8XYZ"
                        operation.result_payload = {
                            "Result": {
                                "ResultParameters": {
                                    "ResultParameter": [
                                        {"Key": "TransactionReceipt", "Value": "NHL61H8XYZ"},
                                    ]
                                }
                            }
                        }
                        operation.save(
                            update_fields=[
                                "status",
                                "summary",
                                "mpesa_reference",
                                "result_payload",
                                "updated_at",
                            ]
                        )
                        return operation

                    wait.side_effect = mark_success
                    response = self.client.post(
                        self._url(
                            User.Role.IT_SUPPORT, "paybill:money-request-review", pk=req.pk
                        ),
                        {"intent": "approve"},
                    )
        self.assertRedirects(
            response,
            self._url(User.Role.IT_SUPPORT, "paybill:transactions"),
            fetch_redirect_response=False,
        )
        req.refresh_from_db()
        self.assertEqual(req.status, MoneyRequest.Status.PAID)
        self.assertEqual(req.mpesa_reference, "NHL61H8XYZ")
        self.assertIsNotNone(req.daraja_operation_id)
        self.assertEqual(req.daraja_operation.kind, DarajaOperation.Kind.B2C)
        self.assertEqual(req.daraja_operation.mpesa_reference, "NHL61H8XYZ")
        self.assertTrue(mock_req.called)


class MpesaReferenceCaptureTests(TestCase):
    def setUp(self):
        from integrations.models import DarajaConfig

        self.paybill = PaybillAccount.objects.create(
            paybill_number="888222",
            account_name="Hub Paybill Capture",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="300031",
            password="test-pass-123",
            email="employee.capture@example.com",
            first_name="Cap",
            last_name="Ture",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        config = DarajaConfig.load()
        config.paybill_account = self.paybill
        config.shortcode = "888222"
        config.save(update_fields=["paybill_account", "shortcode", "updated_at"])

    def test_result_callback_persists_mpesa_reference_everywhere(self):
        from integrations.callbacks import apply_result_callback
        from integrations.models import DarajaOperation
        from paybill.models import LedgerEntry

        operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            status=DarajaOperation.Status.QUEUED,
            destination="254712345678",
            amount=Decimal("250.00"),
            originator_conversation_id="ORIG_CAPTURE_1",
            conversation_id="AG_CAPTURE_1",
        )
        MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.TRAVEL,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("250.00"),
            reason="Site visit",
            status=MoneyRequest.Status.APPROVED,
            daraja_operation=operation,
        )
        apply_result_callback(
            {
                "Result": {
                    "ResultType": 0,
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "OriginatorConversationID": "ORIG_CAPTURE_1",
                    "ConversationID": "AG_CAPTURE_1",
                    "TransactionID": "NLJ7RT61SV",
                    "ResultParameters": {
                        "ResultParameter": [
                            {"Key": "TransactionAmount", "Value": 250},
                            {"Key": "TransactionReceipt", "Value": "NLJ7RT61SV"},
                            {
                                "Key": "ReceiverPartyPublicName",
                                "Value": "254712345678 - Test",
                            },
                        ]
                    },
                }
            }
        )
        operation.refresh_from_db()
        req = MoneyRequest.objects.get(daraja_operation=operation)
        entry = LedgerEntry.objects.get(reference="NLJ7RT61SV")
        self.assertEqual(operation.mpesa_reference, "NLJ7RT61SV")
        self.assertEqual(req.mpesa_reference, "NLJ7RT61SV")
        self.assertEqual(req.status, MoneyRequest.Status.PAID)
        self.assertEqual(entry.mpesa_reference, "NLJ7RT61SV")
        self.assertEqual(entry.expense_category, "Travel")
        self.assertEqual(entry.expense_reason, "Site visit")
        self.assertEqual(entry.payer_name, "Cap Ture")
        self.assertEqual(entry.money_request_id, req.pk)


class EnsureLedgerShowsInitiatorCategoryTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="888333",
            account_name="Hub Paybill Init",
            is_active=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="300041",
            password="test-pass-123",
            email="employee.initcat@example.com",
            first_name="Kimathi",
            last_name="Mbae",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        self.it_support = UserModel.objects.create_user(
            staff_code="300042",
            password="test-pass-123",
            email="it.initcat@example.com",
            first_name="IT",
            last_name="Support",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )

    def _url(self, role: str, name: str = "paybill:transactions") -> str:
        token = set_current_role_slug(role_to_slug(role))
        try:
            return reverse(name)
        finally:
            reset_current_role_slug(token)

    def test_approved_request_appears_in_entries_with_initiator_and_category(self):
        from integrations.models import DarajaOperation
        from paybill.services import ensure_money_request_ledger_entry

        operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            status=DarajaOperation.Status.QUEUED,
            destination="254712345678",
            amount=Decimal("1.00"),
        )
        req = MoneyRequest.objects.create(
            requester=self.employee,
            source_paybill=self.paybill,
            category=MoneyRequest.Category.OFFICE,
            destination_type=MoneyRequest.DestinationType.PHONE,
            destination="0712345678",
            amount=Decimal("1.00"),
            reason="testnsubject",
            status=MoneyRequest.Status.APPROVED,
            daraja_operation=operation,
        )
        ensure_money_request_ledger_entry(req, operation)

        self.client.force_login(self.it_support)
        response = self.client.get(self._url(User.Role.IT_SUPPORT))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kimathi Mbae")
        self.assertContains(response, "Office supplies")
        self.assertContains(response, "testnsubject")

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from integrations.models import DarajaOperation
from paybill.forms import CollectionMonitorManualTransferForm
from paybill.manual_transfer import execute_manual_monitor_transfer
from paybill.models import CollectionMonitor, LedgerEntry, MoneyRequest, PaybillAccount

UserModel = get_user_model()


class CollectionMonitorManualTransferFormTests(TestCase):
    def setUp(self):
        self.monitor = CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            collection_code="COLMANUAL01",
            auto_payout_destination_type=MoneyRequest.DestinationType.PHONE,
            auto_payout_destination="254712345678",
        )

    def test_requires_phone_without_saved_destination(self):
        monitor = CollectionMonitor.objects.create(
            label="Empty",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174380",
            collection_code="COLMANUAL03",
        )
        form = CollectionMonitorManualTransferForm(
            data={"amount": "100", "destination": ""},
            monitor=monitor,
        )
        self.assertFalse(form.is_valid())

    def test_phone_uses_saved_destination_when_blank(self):
        form = CollectionMonitorManualTransferForm(
            data={"amount": "50", "destination": ""},
            monitor=self.monitor,
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["destination"], "254712345678")


@patch("paybill.manual_transfer.DarajaConfig.load")
@patch("paybill.manual_transfer.DarajaClient")
@patch("paybill.manual_transfer.callback_urls")
class ExecuteManualMonitorTransferTests(TestCase):
    def setUp(self):
        self.monitor = CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            collection_code="COLMANUAL02",
        )

    def test_phone_b2c(self, mock_urls, mock_client_cls, mock_load):
        mock_urls.return_value = {"result_url": "https://example.com/r", "timeout_url": ""}
        config = mock_load.return_value
        config.b2c_ready = True
        client = MagicMock()
        mock_client_cls.return_value = client
        client.b2c_send.return_value = (
            {"ResponseDescription": "OK"},
            {},
            "254712345678",
        )
        op = execute_manual_monitor_transfer(
            self.monitor,
            amount=Decimal("25"),
            destination="0712345678",
            request=MagicMock(),
        )
        self.assertEqual(op.kind, DarajaOperation.Kind.B2C)
        client.b2c_send.assert_called_once()


class AutomationAccountLiveApiTests(TestCase):
    def setUp(self):
        self.paybill = PaybillAccount.objects.create(
            paybill_number="174379",
            account_name="Shop",
            is_active=True,
        )
        self.admin = UserModel.objects.create_user(
            staff_code="400001",
            password="test-pass-123",
            email="admin.live@example.com",
            role=User.Role.ADMIN,
            is_approved=True,
        )
        self.monitor = CollectionMonitor.objects.create(
            label="Live",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            paybill_account=self.paybill,
            collection_code="COLLIVE01",
        )
        token = set_current_role_slug(role_to_slug(User.Role.ADMIN))
        try:
            self.url = reverse("paybill:automation-account", kwargs={"pk": self.monitor.pk})
        finally:
            reset_current_role_slug(token)
        LedgerEntry.objects.create(
            reference="IN-LIVE-1",
            paybill_account=self.paybill,
            direction=LedgerEntry.Direction.IN,
            amount=Decimal("10.00"),
            account_ref=self.monitor.collection_code,
            status=LedgerEntry.Status.COMPLETED,
            payer_phone="254711111111",
        )
        self.client.force_login(self.admin)

    def test_ledger_poll_json(self):
        response = self.client.get(self.url, {"poll": "ledger", "q": "254711"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["entries"]), 1)

    def test_operation_poll_json(self):
        op = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            status=DarajaOperation.Status.SUCCESS,
            destination="254712345678",
            amount=Decimal("5.00"),
            collection_monitor=self.monitor,
        )
        response = self.client.get(self.url, {"poll": "operation", "operation_id": op.pk})
        self.assertEqual(response.status_code, 200)
        payload = response.json()["operation"]
        self.assertTrue(payload["complete"])
        self.assertTrue(payload["success"])

    @patch("paybill.views.execute_manual_monitor_transfer")
    def test_manual_transfer_ajax_returns_operation(self, mock_execute):
        op = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2C,
            status=DarajaOperation.Status.QUEUED,
            destination="254712345678",
            amount=Decimal("20.00"),
            collection_monitor=self.monitor,
        )
        mock_execute.return_value = op
        response = self.client.post(
            self.url,
            {
                "intent": "manual-transfer",
                "amount": "20",
                "destination": "0712345678",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["operation"]["id"], op.pk)

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from paybill.auto_payout import maybe_auto_payout_inbound
from paybill.forms import CollectionMonitorPayoutForm
from paybill.models import CollectionMonitor, LedgerEntry, PaybillAccount


class CollectionMonitorPayoutFormTests(TestCase):
    def setUp(self):
        self.monitor = CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            collection_code="COLAUTO12345",
        )

    def test_requires_phone_when_auto_enabled(self):
        form = CollectionMonitorPayoutForm(
            data={"auto_payout_enabled": True, "auto_payout_phone": ""},
            instance=self.monitor,
        )
        self.assertFalse(form.is_valid())

    def test_normalizes_client_phone(self):
        form = CollectionMonitorPayoutForm(
            data={"auto_payout_enabled": True, "auto_payout_phone": "0712345678"},
            instance=self.monitor,
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["auto_payout_phone"], "254712345678")


class AutoPayoutTriggerTests(TestCase):
    def setUp(self):
        self.account = PaybillAccount.objects.create(
            paybill_number="174379",
            account_name="Shop",
        )
        self.monitor = CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            paybill_account=self.account,
            collection_code="COLAUTO99999",
            auto_payout_enabled=True,
            auto_payout_phone="254712345678",
        )
        self.entry = LedgerEntry.objects.create(
            reference="IN-TEST-1",
            paybill_account=self.account,
            direction=LedgerEntry.Direction.IN,
            amount=Decimal("100.00"),
            account_ref=self.monitor.collection_code,
            status=LedgerEntry.Status.COMPLETED,
        )

    @patch("paybill.auto_payout.DarajaClient")
    @patch("paybill.auto_payout.DarajaConfig.load")
    def test_queues_b2c_when_enabled(self, mock_load, mock_client_cls):
        config = mock_load.return_value
        config.b2c_ready = True
        client = mock_client_cls.return_value
        client.b2c_send.return_value = (
            {"ResponseDescription": "Accepted"},
            {"Amount": "100"},
            "254712345678",
        )

        op = maybe_auto_payout_inbound(self.monitor, self.entry)
        self.assertIsNotNone(op)
        client.b2c_send.assert_called_once()

    def test_skips_when_disabled(self):
        self.monitor.auto_payout_enabled = False
        self.monitor.save(update_fields=["auto_payout_enabled"])
        self.assertIsNone(maybe_auto_payout_inbound(self.monitor, self.entry))

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from integrations.models import DarajaOperation
from paybill.auto_payout import (
    auto_payout_is_enabled,
    continue_auto_payout_chain,
    maybe_auto_payout_inbound,
    payout_destination_requires_utility,
    should_move_utility_first,
)
from paybill.forms import CollectionMonitorPayoutForm
from paybill.models import CollectionMonitor, LedgerEntry, MoneyRequest, PaybillAccount


class CollectionMonitorPayoutFormTests(TestCase):
    def setUp(self):
        self.monitor = CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            collection_code="COLAUTO12345",
        )

    def test_requires_destination_when_auto_enabled(self):
        form = CollectionMonitorPayoutForm(
            data={
                "auto_payout_enabled": True,
                "auto_payout_utility_first": False,
                "auto_payout_destination_type": MoneyRequest.DestinationType.PHONE,
                "auto_payout_destination": "",
                "auto_payout_account_ref": "",
            },
            instance=self.monitor,
        )
        self.assertFalse(form.is_valid())

    def test_paybill_requires_utility_first(self):
        phone_monitor = CollectionMonitor.objects.create(
            label="Agent phone",
            account_type=CollectionMonitor.AccountType.PHONE,
            identifier="254712345678",
            collection_code="COLPHONE1234",
        )
        form = CollectionMonitorPayoutForm(
            data={
                "auto_payout_enabled": True,
                "auto_payout_utility_first": False,
                "auto_payout_destination_type": MoneyRequest.DestinationType.PAYBILL,
                "auto_payout_destination": "400200",
                "auto_payout_account_ref": "ACC1",
            },
            instance=phone_monitor,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("auto_payout_utility_first", form.errors)

    def test_paybill_requires_account_ref(self):
        form = CollectionMonitorPayoutForm(
            data={
                "auto_payout_enabled": True,
                "auto_payout_utility_first": True,
                "auto_payout_destination_type": MoneyRequest.DestinationType.PAYBILL,
                "auto_payout_destination": "400200",
                "auto_payout_account_ref": "",
            },
            instance=self.monitor,
        )
        self.assertFalse(form.is_valid())

    def test_paybill_collection_phone_payout_can_save_without_utility_flag(self):
        form = CollectionMonitorPayoutForm(
            data={
                "auto_payout_enabled": True,
                "auto_payout_destination_type": MoneyRequest.DestinationType.PHONE,
                "auto_payout_destination": "0712345678",
                "auto_payout_account_ref": "",
            },
            instance=self.monitor,
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertFalse(saved.auto_payout_utility_first)


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
            auto_payout_utility_first=True,
            auto_payout_destination_type=MoneyRequest.DestinationType.PHONE,
            auto_payout_destination="254712345678",
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

    @patch("paybill.auto_payout.callback_urls")
    @patch("paybill.auto_payout.DarajaClient")
    @patch("paybill.auto_payout.DarajaConfig.load")
    def test_paybill_collection_starts_with_utility_move(self, mock_load, mock_client_cls, mock_urls):
        mock_urls.return_value = {"result_url": "https://hub.test/daraja/result/", "timeout_url": "https://hub.test/daraja/timeout/"}
        config = mock_load.return_value
        config.b2b_ready = True
        config.b2c_ready = True
        config.result_url = "https://hub.test/daraja/result/"
        client = mock_client_cls.return_value
        client.utility_to_working.return_value = (
            {"ResponseDescription": "Accepted"},
            {"Amount": "100"},
            "600996",
        )

        self.assertTrue(should_move_utility_first(self.monitor))
        op = maybe_auto_payout_inbound(self.monitor, self.entry)
        self.assertIsNotNone(op)
        self.assertEqual(op.kind, DarajaOperation.Kind.B2B)
        client.utility_to_working.assert_called_once()
        client.b2c_send.assert_not_called()

    @patch("paybill.auto_payout.callback_urls")
    @patch("paybill.auto_payout.DarajaClient")
    @patch("paybill.auto_payout.DarajaConfig.load")
    def test_utility_success_chains_to_b2c(self, mock_load, mock_client_cls, mock_urls):
        mock_urls.return_value = {"result_url": "https://hub.test/daraja/result/", "timeout_url": "https://hub.test/daraja/timeout/"}
        config = mock_load.return_value
        config.b2c_ready = True
        client = mock_client_cls.return_value
        client.b2c_send.return_value = (
            {"ResponseDescription": "Accepted"},
            {"Amount": "100"},
            "254712345678",
        )
        utility_op = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2B,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            amount=Decimal("100.00"),
            account_ref="UTILITY-WORKING",
            collection_monitor=self.monitor,
            request_payload={
                "auto_payout_ledger_id": self.entry.pk,
                "auto_payout_chain": {
                    "phase": "utility",
                    "monitor_id": self.monitor.pk,
                    "ledger_entry_id": self.entry.pk,
                },
            },
            summary="Utility moved",
        )

        continue_auto_payout_chain(utility_op)
        client.b2c_send.assert_called_once()
        payout = DarajaOperation.objects.filter(
            kind=DarajaOperation.Kind.B2C,
            request_payload__auto_payout_ledger_id=self.entry.pk,
        ).first()
        self.assertIsNotNone(payout)

    @patch("paybill.auto_payout.callback_urls")
    @patch("paybill.auto_payout.DarajaClient")
    @patch("paybill.auto_payout.DarajaConfig.load")
    def test_phone_payout_without_utility_flag_sends_b2c_directly(self, mock_load, mock_client_cls, mock_urls):
        mock_urls.return_value = {"result_url": "https://hub.test/daraja/result/", "timeout_url": "https://hub.test/daraja/timeout/"}
        self.monitor.auto_payout_utility_first = False
        self.monitor.save(update_fields=["auto_payout_utility_first"])
        config = mock_load.return_value
        config.b2c_ready = True
        config.b2b_ready = False
        client = mock_client_cls.return_value
        client.b2c_send.return_value = (
            {"ResponseDescription": "Accepted"},
            {"Amount": "100"},
            "254712345678",
        )

        op = maybe_auto_payout_inbound(self.monitor, self.entry)
        self.assertIsNotNone(op)
        self.assertEqual(op.kind, DarajaOperation.Kind.B2C)
        client.b2c_send.assert_called_once()
        client.utility_to_working.assert_not_called()

    @patch("paybill.auto_payout.callback_urls")
    @patch("paybill.auto_payout.DarajaClient")
    @patch("paybill.auto_payout.DarajaConfig.load")
    def test_after_utility_success_inbound_retry_sends_b2c(self, mock_load, mock_client_cls, mock_urls):
        mock_urls.return_value = {"result_url": "https://hub.test/daraja/result/", "timeout_url": "https://hub.test/daraja/timeout/"}
        config = mock_load.return_value
        config.b2c_ready = True
        client = mock_client_cls.return_value
        client.b2c_send.return_value = (
            {"ResponseDescription": "Accepted"},
            {"Amount": "100"},
            "254712345678",
        )
        DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2B,
            status=DarajaOperation.Status.SUCCESS,
            destination="600996",
            amount=Decimal("100.00"),
            account_ref="UTILITY-WORKING",
            collection_monitor=self.monitor,
            request_payload={
                "auto_payout_ledger_id": self.entry.pk,
                "auto_payout_chain": {
                    "phase": "utility",
                    "monitor_id": self.monitor.pk,
                    "ledger_entry_id": self.entry.pk,
                },
            },
            summary="Utility moved",
        )

        op = maybe_auto_payout_inbound(self.monitor, self.entry)
        self.assertIsNotNone(op)
        self.assertEqual(op.kind, DarajaOperation.Kind.B2C)
        client.b2c_send.assert_called_once()

    def test_skips_when_disabled(self):
        self.monitor.auto_payout_enabled = False
        self.monitor.save(update_fields=["auto_payout_enabled"])
        self.assertFalse(auto_payout_is_enabled(self.monitor))
        self.assertIsNone(maybe_auto_payout_inbound(self.monitor, self.entry))

    def test_paybill_payout_destination_always_needs_utility_move(self):
        self.monitor.auto_payout_utility_first = False
        self.monitor.auto_payout_destination_type = MoneyRequest.DestinationType.PAYBILL
        self.monitor.auto_payout_destination = "400200"
        self.monitor.auto_payout_account_ref = "ACC1"
        self.monitor.save()
        self.assertTrue(payout_destination_requires_utility(self.monitor))
        self.assertTrue(should_move_utility_first(self.monitor))

    @patch("paybill.auto_payout.callback_urls")
    @patch("paybill.auto_payout.DarajaClient")
    @patch("paybill.auto_payout.DarajaConfig.load")
    def test_paybill_payout_starts_utility_even_when_flag_off(self, mock_load, mock_client_cls, mock_urls):
        mock_urls.return_value = {"result_url": "https://hub.test/daraja/result/", "timeout_url": "https://hub.test/daraja/timeout/"}
        self.monitor.auto_payout_utility_first = False
        self.monitor.auto_payout_destination_type = MoneyRequest.DestinationType.PAYBILL
        self.monitor.auto_payout_destination = "400200"
        self.monitor.auto_payout_account_ref = "ACC1"
        self.monitor.save()
        config = mock_load.return_value
        config.b2b_ready = True
        client = mock_client_cls.return_value
        client.utility_to_working.return_value = (
            {"ResponseDescription": "Accepted"},
            {"Amount": "100"},
            "600996",
        )

        op = maybe_auto_payout_inbound(self.monitor, self.entry)
        self.assertIsNotNone(op)
        client.utility_to_working.assert_called_once()
        client.b2b_send.assert_not_called()

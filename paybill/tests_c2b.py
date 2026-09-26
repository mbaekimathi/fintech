from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from integrations.c2b import post_c2b_ledger, validate_c2b_payment
from paybill.automation import monitor_ledger_queryset, monitor_ledger_totals
from paybill.models import CollectionMonitor, LedgerEntry, PaybillAccount


class C2bCallbackTests(TestCase):
    def setUp(self):
        self.account = PaybillAccount.objects.create(
            paybill_number="174379",
            account_name="Test paybill",
        )
        CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            paybill_account=self.account,
        )

    def test_validation_accepts_monitored_shortcode(self):
        payload = {
            "BusinessShortCode": "174379",
            "TransAmount": "100.00",
            "BillRefNumber": "ACC1",
        }
        result = validate_c2b_payment(payload)
        self.assertEqual(result["ResultCode"], 0)

    def test_validation_rejects_unknown_shortcode(self):
        result = validate_c2b_payment({"BusinessShortCode": "999999", "TransAmount": "10"})
        self.assertNotEqual(result["ResultCode"], 0)

    def test_monitor_ledger_lists_paybill_movements(self):
        monitor = CollectionMonitor.objects.get(label="Shop")
        LedgerEntry.objects.create(
            reference="OUT-1",
            paybill_account=self.account,
            direction=LedgerEntry.Direction.OUT,
            amount=Decimal("50.00"),
            account_ref="EXP",
            status=LedgerEntry.Status.COMPLETED,
            narrative="Payout test",
        )
        self.assertEqual(monitor_ledger_queryset(monitor).count(), 1)
        totals = monitor_ledger_totals(monitor)
        self.assertEqual(totals["outbound"], Decimal("50.00"))

    def test_confirmation_creates_inbound_ledger(self):
        payload = {
            "TransID": "QAB123XYZ",
            "TransAmount": "250.00",
            "BusinessShortCode": "174379",
            "BillRefNumber": "ACC1",
            "MSISDN": "254708374149",
            "FirstName": "Jane",
            "TransactionType": "Pay Bill",
        }
        entry = post_c2b_ledger(payload)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.reference, "QAB123XYZ")
        self.assertEqual(entry.amount, Decimal("250.00"))
        self.assertEqual(entry.direction, LedgerEntry.Direction.IN)
        self.assertEqual(entry.paybill_account_id, self.account.pk)

    def test_confirmation_api(self):
        url = reverse("integrations:daraja-c2b-confirmation")
        response = self.client.post(
            url,
            data={
                "TransID": "QAB999",
                "TransAmount": "50",
                "BusinessShortCode": "174379",
                "MSISDN": "254708374149",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LedgerEntry.objects.filter(reference="QAB999").exists())

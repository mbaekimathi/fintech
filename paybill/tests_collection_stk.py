from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from integrations.callbacks import apply_stk_callback
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import CollectionMonitor, LedgerEntry, PaybillAccount


class CollectionStkLedgerTests(TestCase):
    def setUp(self):
        self.account = PaybillAccount.objects.create(
            paybill_number="174379",
            account_name="Shop paybill",
        )
        self.monitor = CollectionMonitor.objects.create(
            label="Shop",
            account_type=CollectionMonitor.AccountType.PAYBILL,
            identifier="174379",
            paybill_account=self.account,
            collection_code="COL123456789",
        )
        self.operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.STK,
            status=DarajaOperation.Status.QUEUED,
            destination="254712345678",
            amount=Decimal("1500.00"),
            account_ref=self.monitor.collection_code,
            collection_monitor=self.monitor,
            checkout_request_id="ws_CO_123",
            merchant_request_id="mr_123",
        )

    def test_stk_callback_posts_inbound_ledger_for_collection_monitor(self):
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "mr_123",
                    "CheckoutRequestID": "ws_CO_123",
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 1500},
                            {"Name": "MpesaReceiptNumber", "Value": "TH123ABC"},
                            {"Name": "PhoneNumber", "Value": 254712345678},
                        ]
                    },
                }
            }
        }
        apply_stk_callback(payload)
        entry = LedgerEntry.objects.get(reference="TH123ABC")
        self.assertEqual(entry.amount, Decimal("1500"))
        self.assertEqual(entry.direction, LedgerEntry.Direction.IN)
        self.assertEqual(entry.account_ref, self.monitor.collection_code)
        self.assertEqual(entry.paybill_account_id, self.account.pk)

    def test_stk_callback_api_accepts_raw_json_body(self):
        url = reverse("integrations:daraja-stk-callback")
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "mr_123",
                    "CheckoutRequestID": "ws_CO_123",
                    "ResultCode": 0,
                    "ResultDesc": "Success",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 500},
                            {"Name": "MpesaReceiptNumber", "Value": "TH999XYZ"},
                            {"Name": "PhoneNumber", "Value": 254712345678},
                        ]
                    },
                }
            }
        }
        response = self.client.post(url, data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LedgerEntry.objects.filter(reference="TH999XYZ").exists())

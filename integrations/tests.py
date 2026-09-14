from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from integrations.models import DarajaConfig


REQUIRED_DARAJA_FIELDS = (
    "environment",
    "hub_paybill",
    "shortcode",
    "org_shortcode",
    "till_number",
    "consumer_key",
    "consumer_secret",
    "passkey",
    "stk_transaction_type",
    "stk_account_reference",
    "stk_transaction_desc",
    "stk_callback_url",
    "initiator_name",
    "security_credential",
    "result_url",
    "timeout_url",
    "balance_identifier_type",
    "balance_remarks",
    "b2c_enabled",
    "b2c_command_id",
    "b2c_remarks",
    "b2c_occasion",
    "b2b_enabled",
    "b2b_sender_identifier_type",
    "b2b_paybill_command",
    "b2b_till_command",
    "b2b_remarks",
)


def make_user(*, staff_code: str, role: str) -> User:
    return User.objects.create_user(
        staff_code=staff_code,
        password="135790",
        email=f"{staff_code}@nexus.test",
        first_name="Test",
        last_name=role.replace("_", " ").title(),
        role=role,
        is_approved=True,
        is_active=True,
    )


class DarajaSettingsTests(TestCase):
    def setUp(self):
        self.url = reverse("core:daraja")
        self.admin = make_user(staff_code="100011", role=User.Role.ADMIN)
        self.employee = make_user(staff_code="200022", role=User.Role.EMPLOYEE)

    def test_settings_daraja_url(self):
        self.assertEqual(self.url, "/settings/daraja/")

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_employee_forbidden(self):
        self.client.force_login(self.employee)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_admin_form_includes_stk_balance_and_payout_fields(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        for name in REQUIRED_DARAJA_FIELDS:
            self.assertIn(name, form.fields, msg=name)
        self.assertContains(response, "STK push")
        self.assertContains(response, "Live paybill balance")
        self.assertContains(response, "Send to a phone number")
        self.assertContains(response, "Send to another paybill or till")
        self.assertContains(response, "Paybill number")
        self.assertNotContains(response, "Select a paybill account")

    def test_admin_saves_daraja_setup(self):
        self.client.force_login(self.admin)
        payload = {
            "environment": DarajaConfig.Environment.SANDBOX,
            "consumer_key": "sandbox-consumer-key",
            "consumer_secret": "sandbox-consumer-secret",
            "stk_transaction_type": DarajaConfig.StkTransactionType.PAYBILL,
            "balance_identifier_type": DarajaConfig.IdentifierType.SHORTCODE,
            "b2c_enabled": "on",
            "b2c_command_id": DarajaConfig.B2CCommand.BUSINESS,
            "b2b_enabled": "on",
            "b2b_sender_identifier_type": DarajaConfig.IdentifierType.SHORTCODE,
            "b2b_paybill_command": DarajaConfig.B2BCommand.PAYBILL,
            "b2b_till_command": DarajaConfig.B2BCommand.BUY_GOODS,
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.consumer_key, "sandbox-consumer-key")
        self.assertEqual(config.shortcode, "174379")
        self.assertEqual(config.org_shortcode, "600996")
        self.assertTrue(config.b2c_enabled)
        self.assertTrue(config.b2b_enabled)
        self.assertTrue(config.stk_ready)
        self.assertTrue(config.balance_ready)
        self.assertTrue(config.b2c_ready)
        self.assertTrue(config.b2b_ready)

    def test_save_keeps_portal_initiator_fields(self):
        self.client.force_login(self.admin)
        payload = {
            "environment": DarajaConfig.Environment.SANDBOX,
            "consumer_key": "sandbox-consumer-key",
            "consumer_secret": "sandbox-consumer-secret",
            "org_shortcode": "600984",
            "initiator_name": "Safaricomapi",
            "security_credential": "PortalPassword1",
            "stk_transaction_type": DarajaConfig.StkTransactionType.PAYBILL,
            "balance_identifier_type": DarajaConfig.IdentifierType.SHORTCODE,
            "b2c_enabled": "on",
            "b2c_command_id": DarajaConfig.B2CCommand.BUSINESS,
            "b2b_enabled": "on",
            "b2b_sender_identifier_type": DarajaConfig.IdentifierType.SHORTCODE,
            "b2b_paybill_command": DarajaConfig.B2BCommand.PAYBILL,
            "b2b_till_command": DarajaConfig.B2BCommand.BUY_GOODS,
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.org_shortcode, "600984")
        self.assertEqual(config.initiator_name, "Safaricomapi")
        self.assertEqual(config.security_credential, "PortalPassword1")

    def test_production_saves_typed_paybill(self):
        from paybill.models import PaybillAccount

        self.client.force_login(self.admin)
        payload = {
            "environment": DarajaConfig.Environment.PRODUCTION,
            "hub_paybill": "888555",
            "consumer_key": "live-consumer-key",
            "consumer_secret": "live-consumer-secret",
            "passkey": "live-passkey",
            "initiator_name": "liveinitiator",
            "security_credential": "LivePassword1",
            "stk_transaction_type": DarajaConfig.StkTransactionType.PAYBILL,
            "stk_callback_url": "https://fin.richcom.co.ke/api/v1/daraja/stk/callback/",
            "result_url": "https://fin.richcom.co.ke/api/v1/daraja/result/",
            "timeout_url": "https://fin.richcom.co.ke/api/v1/daraja/timeout/",
            "balance_identifier_type": DarajaConfig.IdentifierType.SHORTCODE,
            "b2c_enabled": "on",
            "b2c_command_id": DarajaConfig.B2CCommand.BUSINESS,
            "b2b_enabled": "on",
            "b2b_sender_identifier_type": DarajaConfig.IdentifierType.SHORTCODE,
            "b2b_paybill_command": DarajaConfig.B2BCommand.PAYBILL,
            "b2b_till_command": DarajaConfig.B2BCommand.BUY_GOODS,
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.environment, DarajaConfig.Environment.PRODUCTION)
        self.assertEqual(config.shortcode, "888555")
        self.assertEqual(config.org_shortcode, "888555")
        self.assertEqual(config.paybill_account.paybill_number, "888555")
        self.assertTrue(PaybillAccount.objects.filter(paybill_number="888555").exists())
        self.assertEqual(config.consumer_key, "live-consumer-key")
        self.assertNotEqual(config.shortcode, "174379")


class DarajaPayoutHelperTests(TestCase):
    def test_sandbox_stk_till_does_not_pay_out(self):
        config = DarajaConfig.load()
        config.environment = DarajaConfig.Environment.SANDBOX
        config.shortcode = "174379"
        config.org_shortcode = ""
        self.assertEqual(config.payout_shortcode, "600996")

    def test_format_account_balances(self):
        from integrations.callbacks import format_account_balances

        raw = "Working Account|KES|346499.00|346499.00|0.00|0.00&Utility Account|KES|12.50|12.50|0.00|0.00"
        self.assertEqual(format_account_balances(raw), "Working KES 346499.00 · Utility KES 12.50")

    def test_encrypts_plaintext_sandbox_password(self):
        from integrations.security_credential import encrypt_security_credential, looks_encrypted

        encrypted = encrypt_security_credential("Safaricom123!!", sandbox=True)
        self.assertTrue(looks_encrypted(encrypted))
        self.assertEqual(encrypt_security_credential(encrypted, sandbox=True), encrypted)

    def test_balance_and_b2c_use_org_shortcode(self):
        from unittest.mock import patch

        from integrations.daraja_client import DarajaClient

        config = DarajaConfig.load()
        config.environment = DarajaConfig.Environment.SANDBOX
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
        ack = {
            "ResponseCode": "0",
            "ResponseDescription": "Accept the service request successfully.",
            "ConversationID": "AG_1",
            "OriginatorConversationID": "ORIG_1",
        }
        client = DarajaClient(config)
        with patch.object(client, "access_token", return_value="token"):
            with patch("integrations.daraja_client._json_request") as mock_req:
                mock_req.return_value = (200, ack)
                _body, payload, party_a = client.account_balance(
                    result_url=config.result_url,
                    timeout_url=config.timeout_url,
                )
                self.assertEqual(party_a, "600996")
                self.assertEqual(payload["PartyA"], "600996")
                self.assertNotEqual(payload["SecurityCredential"], "Safaricom123!!")
                _body, send_payload, dest = client.b2c_send(
                    phone="254708374149",
                    amount=1,
                    result_url=config.result_url,
                    timeout_url=config.timeout_url,
                )
        self.assertEqual(dest, "254708374149")
        self.assertEqual(send_payload["PartyA"], "600996")
        self.assertEqual(send_payload["Occassion"], "Payment")

    def test_callback_uses_live_ngrok_not_stale_saved_url(self):
        from unittest.mock import patch

        from integrations.daraja_client import DarajaClient

        config = DarajaConfig.load()
        client = DarajaClient(config)
        stale = "https://old.ngrok-free.app/api/v1/daraja/result/"
        with patch("integrations.daraja.detect_ngrok_base", return_value="https://0ba3-41-90-173-25.ngrok-free.app"):
            url = client._callback(stale, "")
        self.assertEqual(url, "https://0ba3-41-90-173-25.ngrok-free.app/api/v1/daraja/result/")


class DarajaTestPageTests(TestCase):
    def setUp(self):
        self.url = reverse("core:daraja-test")
        self.admin = make_user(staff_code="100033", role=User.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_test_page_and_poll(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View account balance")
        self.assertContains(response, "Send money")
        poll = self.client.get(self.url, {"poll": "1"})
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.json()["operations"], [])

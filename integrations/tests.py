from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.role_urls import reset_current_role_slug, role_to_slug, set_current_role_slug
from integrations.models import DarajaConfig


REQUIRED_DARAJA_APP_FIELDS = (
    "environment",
    "channel",
    "hub_paybill",
    "shortcode",
    "org_shortcode",
    "till_number",
    "consumer_key",
    "consumer_secret",
)

REQUIRED_SECTION_FIELDS = {
    "core:daraja-stk": (
        "passkey",
        "stk_transaction_type",
        "stk_account_reference",
        "stk_transaction_desc",
        "stk_callback_url",
    ),
    "core:daraja-balance": (
        "initiator_name",
        "security_credential",
        "result_url",
        "timeout_url",
        "balance_identifier_type",
        "balance_remarks",
    ),
    "core:daraja-b2c": (
        "b2c_enabled",
        "b2c_command_id",
        "b2c_remarks",
        "b2c_occasion",
    ),
    "core:daraja-b2b": (
        "b2b_enabled",
        "b2b_sender_identifier_type",
        "b2b_paybill_command",
        "b2b_till_command",
        "b2b_remarks",
    ),
    "core:daraja-agent": (
        "agent_shop_enabled",
        "agent_channel",
        "agent_till_number",
        "agent_head_office",
        "agent_store_number",
        "agent_operator_id",
        "agent_api_enabled",
        "agent_use_shared_app",
        "agent_consumer_key",
        "agent_consumer_secret",
        "agent_initiator_name",
        "agent_security_credential",
        "agent_api_base_url",
        "agent_deposit_path",
        "agent_withdraw_path",
        "agent_deposit_command",
        "agent_withdraw_command",
        "agent_deposit_callback_url",
        "agent_withdraw_callback_url",
        "agent_result_url",
        "agent_timeout_url",
        "agent_track_commission",
        "agent_api_notes",
        "agent_cash_in_enabled",
        "agent_cash_out_enabled",
        "agent_min_amount",
        "agent_max_amount",
        "agent_daily_limit",
        "agent_cash_in_fee",
        "agent_cash_out_fee",
        "agent_cash_in_account_ref",
        "agent_float_warn_kes",
        "agent_receipt_prefix",
    ),
}


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


def role_url(name: str, role: str, *args) -> str:
    token = set_current_role_slug(role_to_slug(role))
    try:
        return reverse(name, args=args)
    finally:
        reset_current_role_slug(token)


class DarajaSettingsTests(TestCase):
    def setUp(self):
        self.admin = make_user(staff_code="100011", role=User.Role.ADMIN)
        self.employee = make_user(staff_code="200022", role=User.Role.EMPLOYEE)
        self.url = role_url("core:daraja", User.Role.ADMIN)

    def test_settings_daraja_url(self):
        self.assertEqual(self.url, "/as/admin/settings/daraja/")

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_employee_forbidden(self):
        self.client.force_login(self.employee)
        response = self.client.get(role_url("core:daraja", User.Role.EMPLOYEE))
        self.assertEqual(response.status_code, 403)

    def test_unified_form_includes_all_sections(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        for name in REQUIRED_DARAJA_APP_FIELDS:
            self.assertIn(name, form.fields, msg=name)
        for fields in REQUIRED_SECTION_FIELDS.values():
            for field in fields:
                self.assertIn(field, form.fields, msg=field)
        self.assertContains(response, "Daraja setup")
        self.assertContains(response, "App credentials")
        self.assertContains(response, "STK collect")
        self.assertContains(response, "Balance &amp; initiator")
        self.assertContains(response, "Agent shop")
        self.assertContains(response, "Test credentials")
        self.assertNotContains(response, "Select a paybill account")

    def test_legacy_daraja_urls_render_unified_page(self):
        self.client.force_login(self.admin)
        anchors = {
            "core:daraja-stk": "stk",
            "core:daraja-balance": "balance",
            "core:daraja-b2c": "payouts",
            "core:daraja-b2b": "payouts",
            "core:daraja-agent": "agent",
        }
        for name, anchor in anchors.items():
            response = self.client.get(role_url(name, User.Role.ADMIN))
            self.assertEqual(response.status_code, 200, msg=name)
            self.assertEqual(response.context["scroll_anchor"], anchor, msg=name)
            self.assertContains(response, 'data-daraja-setup', msg_prefix=name)

    def test_b2b_enable_intent_turns_on_without_checkbox(self):
        self.client.force_login(self.admin)
        self.client.post(
            self.url,
            {
                "environment": DarajaConfig.Environment.SANDBOX,
                "channel": "PAYBILL",
                "consumer_key": "sandbox-consumer-key",
                "consumer_secret": "sandbox-consumer-secret",
            },
        )
        config = DarajaConfig.load()
        config.b2b_enabled = False
        config.save(update_fields=["b2b_enabled"])
        response = self.client.post(self.url, {"intent": "enable"}, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertTrue(config.b2b_enabled)
        self.assertEqual(config.b2b_paybill_command, DarajaConfig.B2BCommand.PAYBILL)
        self.assertEqual(config.b2b_till_command, DarajaConfig.B2BCommand.BUY_GOODS)

    def test_admin_saves_daraja_setup(self):
        self.client.force_login(self.admin)
        payload = {
            'environment': DarajaConfig.Environment.SANDBOX,
            'channel': 'PAYBILL',
            'consumer_key': 'sandbox-consumer-key',
            'consumer_secret': 'sandbox-consumer-secret',
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.consumer_key, 'sandbox-consumer-key')
        self.assertEqual(config.shortcode, '174379')
        self.assertEqual(config.org_shortcode, '600996')
        self.assertTrue(config.b2c_enabled)
        self.assertTrue(config.b2b_enabled)
        self.assertTrue(config.stk_ready)
        self.assertTrue(config.balance_ready)
        self.assertTrue(config.b2c_ready)
        self.assertTrue(config.b2b_ready)
        self.assertFalse(config.agent_shop_enabled)

    def _sandbox_base(self):
        return {
            "environment": DarajaConfig.Environment.SANDBOX,
            "channel": "PAYBILL",
            "consumer_key": "sandbox-consumer-key",
            "consumer_secret": "sandbox-consumer-secret",
        }

    def test_admin_saves_agent_shop_logic(self):
        self.client.force_login(self.admin)
        payload = {
            **self._sandbox_base(),
            'agent_shop_enabled': 'on',
            'agent_channel': DarajaConfig.AgentChannel.BUSINESS,
            'agent_use_shared_app': 'on',
            'agent_track_commission': 'on',
            'agent_cash_in_enabled': 'on',
            'agent_cash_out_enabled': 'on',
            'agent_min_amount': '50',
            'agent_max_amount': '40000',
            'agent_daily_limit': '150000',
            'agent_cash_in_fee': '5',
            'agent_cash_out_fee': '10',
            'agent_cash_in_account_ref': 'SHOP01',
            'agent_float_warn_kes': '2500',
            'agent_receipt_prefix': 'NX',
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertTrue(config.agent_shop_enabled)
        self.assertTrue(config.agent_cash_in_enabled)
        self.assertTrue(config.agent_cash_out_enabled)
        self.assertTrue(config.b2c_enabled)
        self.assertEqual(str(config.agent_min_amount), '50.00')
        self.assertEqual(str(config.agent_max_amount), '40000.00')
        self.assertEqual(str(config.agent_daily_limit), '150000.00')
        self.assertEqual(str(config.agent_cash_in_fee), '5.00')
        self.assertEqual(str(config.agent_cash_out_fee), '10.00')
        self.assertEqual(config.agent_cash_in_account_ref, 'SHOP01')
        self.assertEqual(str(config.agent_float_warn_kes), '2500.00')
        self.assertEqual(config.agent_receipt_prefix, 'NX')
        self.assertTrue(config.agent_shop_ready)


    def test_admin_saves_safaricom_agent_future_config(self):
        self.client.force_login(self.admin)
        payload = {
            **self._sandbox_base(),
            'agent_shop_enabled': 'on',
            'agent_channel': DarajaConfig.AgentChannel.SAFARICOM,
            'agent_api_enabled': 'on',
            'agent_use_shared_app': 'on',
            'agent_track_commission': 'on',
            'agent_till_number': '123456',
            'agent_head_office': '654321',
            'agent_store_number': 'STORE-1',
            'agent_deposit_path': 'mpesa/agent/v1/deposit',
            'agent_withdraw_path': '/mpesa/agent/v1/withdraw',
            'agent_deposit_command': 'AgentDeposit',
            'agent_withdraw_command': 'AgentWithdraw',
            'agent_cash_in_enabled': 'on',
            'agent_cash_out_enabled': 'on',
            'agent_min_amount': '50',
            'agent_max_amount': '70000',
            'agent_daily_limit': '0',
            'agent_cash_in_fee': '0',
            'agent_cash_out_fee': '0',
            'agent_float_warn_kes': '1000',
            'agent_receipt_prefix': 'AG',
            'agent_api_notes': 'Awaiting Safaricom pack',
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.agent_channel, DarajaConfig.AgentChannel.SAFARICOM)
        self.assertTrue(config.agent_api_enabled)
        self.assertEqual(config.agent_till_number, '123456')
        self.assertEqual(config.agent_head_office, '654321')
        self.assertEqual(config.agent_deposit_path, '/mpesa/agent/v1/deposit')
        self.assertEqual(config.agent_withdraw_path, '/mpesa/agent/v1/withdraw')
        self.assertTrue(config.agent_deposit_callback_url)
        self.assertTrue(config.agent_withdraw_callback_url)
        self.assertIn('/api/v1/daraja/agent/deposit/callback/', config.agent_deposit_callback_url)
        self.assertTrue(config.agent_safaricom_config_ready)
        self.assertTrue(config.agent_shop_ready)

    def test_save_keeps_portal_initiator_fields(self):
        self.client.force_login(self.admin)
        payload = {
            'environment': DarajaConfig.Environment.SANDBOX,
            'channel': 'PAYBILL',
            'consumer_key': 'sandbox-consumer-key',
            'consumer_secret': 'sandbox-consumer-secret',
            'org_shortcode': '600984',
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        balance_payload = {
            **self._sandbox_base(),
            'org_shortcode': '600984',
            'initiator_name': 'Safaricomapi',
            'security_credential': 'PortalPassword1',
            'balance_identifier_type': DarajaConfig.IdentifierType.SHORTCODE,
            'balance_remarks': 'Balance',
        }
        response = self.client.post(self.url, balance_payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.org_shortcode, '600984')
        self.assertEqual(config.initiator_name, 'Safaricomapi')
        self.assertEqual(config.security_credential, 'PortalPassword1')

    def test_production_saves_typed_paybill(self):
        from paybill.models import PaybillAccount

        self.client.force_login(self.admin)
        payload = {
            'environment': DarajaConfig.Environment.PRODUCTION,
            'channel': 'PAYBILL',
            'hub_paybill': '888555',
            'consumer_key': 'live-consumer-key',
            'consumer_secret': 'live-consumer-secret',
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.environment, DarajaConfig.Environment.PRODUCTION)
        self.assertEqual(config.shortcode, '888555')
        self.assertEqual(config.org_shortcode, '888555')
        self.assertEqual(config.paybill_account.paybill_number, '888555')
        self.assertTrue(PaybillAccount.objects.filter(paybill_number='888555').exists())
        self.assertEqual(config.consumer_key, 'live-consumer-key')
        self.assertNotEqual(config.shortcode, '174379')
        self.assertEqual(config.stk_transaction_type, DarajaConfig.StkTransactionType.PAYBILL)

    def test_production_saves_typed_till(self):
        self.client.force_login(self.admin)
        payload = {
            'environment': DarajaConfig.Environment.PRODUCTION,
            'channel': 'TILL',
            'hub_paybill': '654321',
            'consumer_key': 'live-consumer-key',
            'consumer_secret': 'live-consumer-secret',
        }
        response = self.client.post(self.url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        config = DarajaConfig.load()
        self.assertEqual(config.stk_transaction_type, DarajaConfig.StkTransactionType.BUY_GOODS)
        self.assertEqual(config.till_number, '654321')
        self.assertEqual(config.shortcode, '654321')
        self.assertEqual(config.org_shortcode, '654321')
        self.assertEqual(config.balance_identifier_type, DarajaConfig.IdentifierType.TILL)
        self.assertEqual(config.b2b_sender_identifier_type, DarajaConfig.IdentifierType.TILL)
        self.assertTrue(config.stk_callback_url)
        self.assertTrue(config.result_url)
        self.assertTrue(config.stk_callback_url.startswith('https://fin.richcom.co.ke/'))


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

    def test_callback_uses_hosted_site_not_stale_ngrok(self):
        from unittest.mock import patch

        from integrations.daraja_client import DarajaClient

        config = DarajaConfig.load()
        client = DarajaClient(config)
        stale = "https://old.ngrok-free.app/api/v1/daraja/result/"
        with patch("integrations.daraja.detect_ngrok_base", return_value="https://0ba3-41-90-173-25.ngrok-free.app"):
            url = client._callback(stale, "")
        self.assertEqual(url, "https://fin.richcom.co.ke/api/v1/daraja/result/")

    def test_form_callback_urls_use_hosted_site(self):
        from integrations.daraja import form_callback_urls

        urls = form_callback_urls()
        self.assertEqual(urls["stk_callback_url"], "https://fin.richcom.co.ke/api/v1/daraja/stk/callback/")
        self.assertEqual(urls["result_url"], "https://fin.richcom.co.ke/api/v1/daraja/result/")
        self.assertEqual(urls["timeout_url"], "https://fin.richcom.co.ke/api/v1/daraja/timeout/")


class DarajaTestPageTests(TestCase):
    def setUp(self):
        self.admin = make_user(staff_code="100033", role=User.Role.ADMIN)
        self.url = role_url("core:daraja-test", User.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_test_page_and_poll(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "STK push")
        self.assertContains(response, "Account balance")
        self.assertContains(response, "Send money")
        self.assertContains(response, "Needs setup")
        self.assertContains(response, "Fix app credentials")
        self.assertContains(response, "Recent results")
        poll = self.client.get(self.url, {"poll": "1"})
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.json()["operations"], [])

    def test_panel_blockers_deduplicate_oauth(self):
        from integrations.daraja import capability_status, panel_blockers

        status = capability_status(DarajaConfig.load())
        stk_only = panel_blockers(status, "stk")
        oauth_msgs = set(status["by_id"]["oauth"]["blockers"])
        for msg in oauth_msgs:
            self.assertNotIn(msg, stk_only)

    def test_capability_status_empty_config(self):
        from integrations.daraja import capability_status

        status = capability_status(DarajaConfig.load())
        self.assertFalse(status["fully_ready"])
        not_ready = {item["id"] for item in status["not_ready"]}
        self.assertIn("oauth", not_ready)
        self.assertIn("stk", not_ready)
        self.assertIn("balance", not_ready)

    def test_capability_status_marks_configured_actions_ready(self):
        from unittest.mock import patch

        from integrations.daraja import apply_sandbox_to_instance, capability_status

        config = DarajaConfig.load()
        apply_sandbox_to_instance(config, None, force=True)
        config.consumer_key = "sandbox-consumer-key"
        config.consumer_secret = "sandbox-consumer-secret"
        config.save()
        probe = {
            "ok": True,
            "state": "connected",
            "title": "Successfully integrated",
            "detail": "Daraja accepted this consumer key and secret on sandbox.",
        }
        with patch("integrations.daraja.probe_daraja", return_value=probe):
            with patch(
                "integrations.daraja.detect_ngrok_base",
                return_value="https://demo.ngrok-free.app",
            ):
                with patch(
                    "integrations.daraja.public_base_url",
                    return_value="https://demo.ngrok-free.app",
                ):
                    status = capability_status(config)
        self.assertTrue(status["by_id"]["oauth"]["ready"])
        self.assertTrue(status["by_id"]["stk"]["ready"])
        self.assertTrue(status["by_id"]["balance"]["ready"])
        self.assertTrue(status["by_id"]["b2c"]["ready"])
        self.assertTrue(status["by_id"]["b2b"]["ready"])
        self.assertTrue(status["by_id"]["callbacks"]["ready"])


class SendMoneyFormTests(TestCase):
    def test_phone_accepts_msisdn(self):
        from integrations.forms import SendMoneyForm

        form = SendMoneyForm(
            data={
                "destination_type": "PHONE",
                "destination": "254708374149",
                "amount": "1",
                "account_ref": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_paybill_rejects_phone_and_requires_account(self):
        from integrations.forms import SendMoneyForm

        bad = SendMoneyForm(
            data={
                "destination_type": "PAYBILL",
                "destination": "254708374149",
                "amount": "1",
                "account_ref": "NEXUS",
            }
        )
        self.assertFalse(bad.is_valid())
        self.assertIn("destination", bad.errors)

        missing_account = SendMoneyForm(
            data={
                "destination_type": "PAYBILL",
                "destination": "600000",
                "amount": "1",
                "account_ref": "",
            }
        )
        self.assertFalse(missing_account.is_valid())
        self.assertIn("account_ref", missing_account.errors)

    def test_till_accepts_shortcode_without_account(self):
        from integrations.forms import SendMoneyForm

        form = SendMoneyForm(
            data={
                "destination_type": "TILL",
                "destination": "600000",
                "amount": "1",
                "account_ref": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)


class DarajaB2BPayloadTests(TestCase):
    def _ready_config(self):
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
        config.b2b_enabled = True
        config.b2b_paybill_command = DarajaConfig.B2BCommand.PAYBILL
        config.b2b_till_command = DarajaConfig.B2BCommand.BUY_GOODS
        config.b2b_sender_identifier_type = DarajaConfig.IdentifierType.SHORTCODE
        return config

    def test_b2b_paybill_and_till_payloads(self):
        from unittest.mock import patch

        from integrations.daraja_client import DarajaClient

        config = self._ready_config()
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
                _body, paybill_payload, dest = client.b2b_send(
                    destination="600000",
                    amount=1,
                    to_till=False,
                    account_ref="NEXUS",
                    result_url=config.result_url,
                    timeout_url=config.timeout_url,
                )
                self.assertEqual(dest, "600000")
                self.assertEqual(paybill_payload["CommandID"], "BusinessPayBill")
                self.assertEqual(paybill_payload["RecieverIdentifierType"], "4")
                self.assertEqual(paybill_payload["AccountReference"], "NEXUS")
                self.assertEqual(paybill_payload["PartyA"], "600996")

                _body, till_payload, till_dest = client.b2b_send(
                    destination="600000",
                    amount=1,
                    to_till=True,
                    account_ref="",
                    result_url=config.result_url,
                    timeout_url=config.timeout_url,
                )
        self.assertEqual(till_dest, "600000")
        self.assertEqual(till_payload["CommandID"], "BusinessBuyGoods")
        self.assertEqual(till_payload["RecieverIdentifierType"], "4")
        self.assertEqual(till_payload["SenderIdentifierType"], "4")
        self.assertEqual(till_payload["PartyA"], "600996")
        self.assertEqual(till_payload["AccountReference"], "NEXUS")

    def test_b2b_rejects_phone_as_destination(self):
        from integrations.daraja_client import DarajaClient, DarajaError

        client = DarajaClient(self._ready_config())
        with self.assertRaises(DarajaError):
            client.b2b_send(
                destination="254708374149",
                amount=1,
                to_till=False,
                account_ref="NEXUS",
                result_url="https://example.test/api/v1/daraja/result/",
                timeout_url="https://example.test/api/v1/daraja/timeout/",
            )

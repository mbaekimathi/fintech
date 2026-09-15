import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.fields import MysqlBooleanEnumField, MysqlChoiceEnumField
from paybill.models import ConnectedSystem, PaybillAccount


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class APICredential(models.Model):
    system = models.ForeignKey(ConnectedSystem, on_delete=models.CASCADE, related_name="credentials")
    name = models.CharField(max_length=80, default="primary")
    key_prefix = models.CharField(max_length=12)
    key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.system.slug}:{self.key_prefix}…"

    @classmethod
    def issue(cls, system: ConnectedSystem, name: str = "primary") -> tuple["APICredential", str]:
        raw = "nx_" + secrets.token_urlsafe(32)
        cred = cls.objects.create(
            system=system,
            name=name,
            key_prefix=raw[:10],
            key_hash=hash_api_key(raw),
        )
        return cred, raw

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])


class DarajaOperation(models.Model):
    class Kind(models.TextChoices):
        STK = "STK", "STK push"
        BALANCE = "BALANCE", "Account balance"
        B2C = "B2C", "Send to phone"
        B2B = "B2B", "Send to paybill or till"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        TIMEOUT = "TIMEOUT", "Timed out"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    destination = models.CharField(max_length=32, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    account_ref = models.CharField(max_length=64, blank=True)
    merchant_request_id = models.CharField(max_length=64, blank=True)
    checkout_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    conversation_id = models.CharField(max_length=64, blank=True, db_index=True)
    originator_conversation_id = models.CharField(max_length=64, blank=True, db_index=True)
    mpesa_reference = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="M-Pesa receipt / transaction reference from Safaricom.",
    )
    result_code = models.CharField(max_length=16, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    result_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daraja_operations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.kind} {self.status} {self.destination}"

    def capture_mpesa_reference(self, receipt: str = "", *, items=None) -> str:
        """Persist the first usable M-Pesa receipt found for this operation."""
        from paybill.services import extract_mpesa_receipt

        value = extract_mpesa_receipt(
            receipt=receipt,
            items=items,
            payload=self.result_payload,
            summary=self.summary,
        )
        if value and self.mpesa_reference != value:
            self.mpesa_reference = value
        return self.mpesa_reference

    def is_fresh_queue(self, seconds: int = 90) -> bool:
        if self.status != self.Status.QUEUED:
            return False
        created = self.created_at
        if timezone.is_naive(created):
            created = timezone.make_aware(created, timezone.get_current_timezone())
        return (timezone.now() - created).total_seconds() < seconds


class DarajaConfig(models.Model):
    class Environment(models.TextChoices):
        SANDBOX = "SANDBOX", "Sandbox"
        PRODUCTION = "PRODUCTION", "Production"

    class StkTransactionType(models.TextChoices):
        PAYBILL = "CustomerPayBillOnline", "Paybill (CustomerPayBillOnline)"
        BUY_GOODS = "CustomerBuyGoodsOnline", "Till / Buy Goods (CustomerBuyGoodsOnline)"

    class IdentifierType(models.TextChoices):
        MSISDN = "1", "Phone number (MSISDN)"
        TILL = "2", "Till number"
        SHORTCODE = "4", "Paybill / organization shortcode"

    class B2CCommand(models.TextChoices):
        BUSINESS = "BusinessPayment", "Business payment"
        SALARY = "SalaryPayment", "Salary payment"
        PROMOTION = "PromotionPayment", "Promotion payment"

    class B2BCommand(models.TextChoices):
        PAYBILL = "BusinessPayBill", "Send to paybill (BusinessPayBill)"
        BUY_GOODS = "BusinessBuyGoods", "Send to till (BusinessBuyGoods)"
        DISBURSE = "DisburseFundsToBusiness", "Disburse to business"
        TRANSFER = "BusinessToBusinessTransfer", "Business to business transfer"

    class AgentChannel(models.TextChoices):
        BUSINESS = "BUSINESS", "Business shop (STK collect + B2C payout)"
        SAFARICOM = "SAFARICOM", "Official Safaricom agent (API when issued)"

    environment = MysqlChoiceEnumField(
        max_length=12,
        choices=Environment.choices,
        default=Environment.SANDBOX,
    )
    consumer_key = models.CharField(max_length=255, blank=True)
    consumer_secret = models.CharField(max_length=512, blank=True)
    shortcode = models.CharField(
        max_length=20,
        blank=True,
        help_text="Your Lipa Na M-Pesa paybill / organization shortcode.",
    )
    org_shortcode = models.CharField(
        max_length=20,
        blank=True,
        help_text="Organization shortcode for account balance, B2C, and B2B. Sandbox Party A / Shortcode 1 is 600996.",
    )
    till_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Buy Goods till, if different from the paybill shortcode.",
    )
    paybill_account = models.ForeignKey(
        PaybillAccount,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daraja_configs",
        help_text="Hub paybill this Daraja app collects into.",
    )
    passkey = models.CharField(max_length=512, blank=True)
    stk_callback_url = models.URLField(max_length=500, blank=True)
    stk_transaction_type = MysqlChoiceEnumField(
        max_length=32,
        choices=StkTransactionType.choices,
        default=StkTransactionType.PAYBILL,
    )
    stk_account_reference = models.CharField(max_length=64, blank=True)
    stk_transaction_desc = models.CharField(max_length=64, blank=True)
    initiator_name = models.CharField(max_length=120, blank=True)
    security_credential = models.TextField(blank=True)
    result_url = models.URLField(max_length=500, blank=True)
    timeout_url = models.URLField(max_length=500, blank=True)
    balance_identifier_type = MysqlChoiceEnumField(
        max_length=2,
        choices=IdentifierType.choices,
        default=IdentifierType.SHORTCODE,
    )
    balance_remarks = models.CharField(max_length=64, blank=True)
    b2c_enabled = MysqlBooleanEnumField(default=False)
    b2c_command_id = MysqlChoiceEnumField(
        max_length=32,
        choices=B2CCommand.choices,
        default=B2CCommand.BUSINESS,
    )
    b2c_remarks = models.CharField(max_length=64, blank=True)
    b2c_occasion = models.CharField(max_length=64, blank=True)
    b2b_enabled = MysqlBooleanEnumField(default=False)
    b2b_sender_identifier_type = MysqlChoiceEnumField(
        max_length=2,
        choices=IdentifierType.choices,
        default=IdentifierType.SHORTCODE,
    )
    b2b_paybill_command = MysqlChoiceEnumField(
        max_length=32,
        choices=B2BCommand.choices,
        default=B2BCommand.PAYBILL,
    )
    b2b_till_command = MysqlChoiceEnumField(
        max_length=32,
        choices=B2BCommand.choices,
        default=B2BCommand.BUY_GOODS,
    )
    b2b_remarks = models.CharField(max_length=64, blank=True)
    agent_shop_enabled = MysqlBooleanEnumField(
        default=False,
        help_text="Turn on agent-shop deposit and withdraw by phone on this shortcode.",
    )
    agent_channel = MysqlChoiceEnumField(
        max_length=16,
        choices=AgentChannel.choices,
        default=AgentChannel.BUSINESS,
        help_text="Business uses STK/B2C on your paybill. Safaricom agent uses official agent APIs after registration.",
    )
    agent_till_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="M-Pesa agent till / outlet number from Safaricom.",
    )
    agent_head_office = models.CharField(
        max_length=20,
        blank=True,
        help_text="Agent head-office shortcode, if different from the till.",
    )
    agent_store_number = models.CharField(
        max_length=32,
        blank=True,
        help_text="Store or outlet reference from your dealer / head office.",
    )
    agent_operator_id = models.CharField(
        max_length=64,
        blank=True,
        help_text="Operator / attendant id if Safaricom issues one for API calls.",
    )
    agent_api_enabled = MysqlBooleanEnumField(
        default=False,
        help_text="Use official agent deposit/withdraw APIs when Safaricom has issued them.",
    )
    agent_use_shared_app = MysqlBooleanEnumField(
        default=True,
        help_text="Reuse the shared Daraja consumer key/secret. Turn off to paste a separate agent app.",
    )
    agent_consumer_key = models.CharField(max_length=255, blank=True)
    agent_consumer_secret = models.CharField(max_length=512, blank=True)
    agent_initiator_name = models.CharField(max_length=120, blank=True)
    agent_security_credential = models.TextField(blank=True)
    agent_api_base_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="API host Safaricom gives you (leave blank to use the shared Daraja host).",
    )
    agent_deposit_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Relative deposit/cash-in path from the Safaricom API pack, e.g. /mpesa/agent/v1/deposit.",
    )
    agent_withdraw_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Relative withdraw/cash-out path from the Safaricom API pack.",
    )
    agent_deposit_command = models.CharField(
        max_length=64,
        blank=True,
        help_text="CommandID or product code for agent deposit, when provided.",
    )
    agent_withdraw_command = models.CharField(
        max_length=64,
        blank=True,
        help_text="CommandID or product code for agent withdraw, when provided.",
    )
    agent_deposit_callback_url = models.URLField(max_length=500, blank=True)
    agent_withdraw_callback_url = models.URLField(max_length=500, blank=True)
    agent_result_url = models.URLField(max_length=500, blank=True)
    agent_timeout_url = models.URLField(max_length=500, blank=True)
    agent_track_commission = MysqlBooleanEnumField(
        default=True,
        help_text="Record Safaricom agent commission when callbacks or statements expose it.",
    )
    agent_api_notes = models.TextField(
        blank=True,
        help_text="Paste product names, sandbox notes, or support ticket refs from Safaricom.",
    )
    agent_cash_in_enabled = MysqlBooleanEnumField(
        default=True,
        help_text="Cash-in / deposit for a customer phone.",
    )
    agent_cash_out_enabled = MysqlBooleanEnumField(
        default=True,
        help_text="Cash-out / withdraw for a customer phone.",
    )
    agent_min_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=10,
        help_text="Minimum KES per cash-in or cash-out.",
    )
    agent_max_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=70000,
        help_text="Maximum KES per cash-in or cash-out.",
    )
    agent_daily_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Max KES per agent per day. Use 0 for no extra daily cap.",
    )
    agent_cash_in_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Your own fee on business-shop cash-in (KES). Not Safaricom commission. 0 = none.",
    )
    agent_cash_out_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Your own fee on business-shop cash-out (KES). Not Safaricom commission. 0 = none.",
    )
    agent_cash_in_account_ref = models.CharField(
        max_length=64,
        blank=True,
        help_text="Default account reference for cash-in (e.g. AGENT or till code).",
    )
    agent_float_warn_kes = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=1000,
        help_text="Warn when live float falls below this amount.",
    )
    agent_receipt_prefix = models.CharField(
        max_length=16,
        blank=True,
        default="AG",
        help_text="Prefix for agent receipt / reference numbers.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daraja_updates",
    )

    class Meta:
        verbose_name = "Daraja setup"
        verbose_name_plural = "Daraja setup"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    def __str__(self):
        env = self.get_environment_display()
        code = self.shortcode or "no shortcode"
        return f"Daraja {env} ({code})"

    @classmethod
    def load(cls) -> "DarajaConfig":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def secret_is_set(self, field: str) -> bool:
        return bool(getattr(self, field, "").strip())

    @property
    def has_app_credentials(self) -> bool:
        return bool(self.consumer_key and self.consumer_secret and self.shortcode)

    @property
    def payout_shortcode(self) -> str:
        org = (self.org_shortcode or "").strip()
        if org:
            return org
        short = (self.shortcode or "").strip()
        if str(self.environment) == self.Environment.SANDBOX and short == "174379":
            return "600996"
        return short

    @property
    def has_initiator(self) -> bool:
        return bool(
            self.initiator_name
            and self.security_credential
            and self.result_url
            and self.timeout_url
            and self.payout_shortcode
        )

    @property
    def stk_ready(self) -> bool:
        return self.has_app_credentials and bool(self.passkey and self.stk_callback_url)

    @property
    def balance_ready(self) -> bool:
        return self.has_app_credentials and self.has_initiator

    @property
    def b2c_ready(self) -> bool:
        return self.b2c_enabled and self.balance_ready and bool(self.b2c_command_id)

    @property
    def b2b_ready(self) -> bool:
        return self.b2b_enabled and self.balance_ready and bool(self.b2b_paybill_command and self.b2b_till_command)

    @property
    def payout_ready(self) -> bool:
        return self.b2c_ready or self.b2b_ready

    @property
    def is_safaricom_agent_channel(self) -> bool:
        return str(self.agent_channel) == self.AgentChannel.SAFARICOM

    @property
    def agent_app_credentials_ready(self) -> bool:
        if self.agent_use_shared_app:
            return self.has_app_credentials
        return bool(self.agent_consumer_key and self.agent_consumer_secret)

    @property
    def agent_safaricom_config_ready(self) -> bool:
        """Identity + credentials + callbacks filled for future official agent APIs."""
        return bool(
            self.agent_api_enabled
            and self.agent_till_number
            and self.agent_app_credentials_ready
            and self.agent_deposit_callback_url
            and self.agent_withdraw_callback_url
            and self.agent_result_url
            and self.agent_timeout_url
        )

    @property
    def agent_cash_in_ready(self) -> bool:
        if not (self.agent_shop_enabled and self.agent_cash_in_enabled):
            return False
        if self.is_safaricom_agent_channel:
            return self.agent_safaricom_config_ready
        return self.stk_ready

    @property
    def agent_cash_out_ready(self) -> bool:
        if not (self.agent_shop_enabled and self.agent_cash_out_enabled):
            return False
        if self.is_safaricom_agent_channel:
            return self.agent_safaricom_config_ready
        return self.b2c_ready

    @property
    def agent_shop_ready(self) -> bool:
        if not self.agent_shop_enabled:
            return False
        if not (self.agent_cash_in_enabled or self.agent_cash_out_enabled):
            return False
        if self.is_safaricom_agent_channel:
            if not self.agent_safaricom_config_ready:
                return False
            # Paths may arrive later with the Safaricom pack; config can still be saved.
            return True
        if self.agent_cash_in_enabled and not self.stk_ready:
            return False
        if self.agent_cash_out_enabled and not self.b2c_ready:
            return False
        return True

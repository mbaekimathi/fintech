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

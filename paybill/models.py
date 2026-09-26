import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def hash_collection_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_collection_code() -> str:
    """Unique STK AccountReference / C2B bill ref (max 12 chars for Daraja STK)."""
    for _ in range(32):
        code = ("C" + secrets.token_hex(5).upper())[:12]
        if not CollectionMonitor.objects.filter(collection_code=code).exists():
            return code
    raise RuntimeError("Could not allocate a collection code.")


class ConnectedSystem(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="connected_systems",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaybillAccount(models.Model):
    class Provider(models.TextChoices):
        MPESA = "MPESA", "M-Pesa"
        AIRTEL = "AIRTEL", "Airtel Money"
        BANK = "BANK", "Bank"
        OTHER = "OTHER", "Other"

    paybill_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=160)
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.MPESA)
    connected_system = models.ForeignKey(
        ConnectedSystem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="paybill_accounts",
    )
    short_code_notes = models.CharField(max_length=160, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["account_name"]
        unique_together = ("paybill_number", "connected_system")

    def __str__(self):
        return f"{self.account_name} ({self.paybill_number})"


class LedgerEntry(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        REVERSED = "REVERSED", "Reversed"

    class Direction(models.TextChoices):
        IN = "IN", "Inbound"
        OUT = "OUT", "Outbound"

    reference = models.CharField(max_length=64, unique=True)
    mpesa_reference = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="M-Pesa receipt / transaction reference when provided by Safaricom.",
    )
    money_request = models.ForeignKey(
        "MoneyRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )
    expense_category = models.CharField(max_length=64, blank=True)
    expense_reason = models.CharField(max_length=255, blank=True)
    paybill_account = models.ForeignKey(
        PaybillAccount,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    connected_system = models.ForeignKey(
        ConnectedSystem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entries",
    )
    direction = models.CharField(max_length=8, choices=Direction.choices, default=Direction.IN)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="KES")
    payer_name = models.CharField(max_length=160, blank=True)
    payer_phone = models.CharField(max_length=20, blank=True)
    account_ref = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.COMPLETED)
    narrative = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_at"]
        indexes = [
            models.Index(fields=["posted_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.reference} {self.amount} {self.currency}"


class MoneyRequest(models.Model):
    """Employee request to send money from the hub paybill."""

    class Category(models.TextChoices):
        TRAVEL = "TRAVEL", "Travel"
        OFFICE = "OFFICE", "Office supplies"
        UTILITIES = "UTILITIES", "Utilities"
        MEALS = "MEALS", "Meals & entertainment"
        CLIENT = "CLIENT", "Client / project"
        EQUIPMENT = "EQUIPMENT", "Equipment"
        OTHER = "OTHER", "Other"

    class DestinationType(models.TextChoices):
        PAYBILL = "PAYBILL", "Paybill"
        TILL = "TILL", "Till (Buy Goods)"
        PHONE = "PHONE", "Phone number"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="money_requests",
    )
    source_paybill = models.ForeignKey(
        PaybillAccount,
        on_delete=models.PROTECT,
        related_name="money_requests",
        help_text="Hub paybill the funds should come from.",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    destination_type = models.CharField(max_length=12, choices=DestinationType.choices)
    destination = models.CharField(max_length=20)
    recipient_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Verified recipient or business name from live lookup.",
    )
    account_ref = models.CharField(
        max_length=64,
        blank=True,
        help_text="Account number when sending to a paybill.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    mpesa_reference = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="M-Pesa receipt / transaction reference after payout succeeds.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_money_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    viewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="viewed_money_requests",
        help_text="Reviewer who opened this request in the app.",
    )
    viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When a reviewer opened this request. Status stays Pending.",
    )
    daraja_operation = models.OneToOneField(
        "integrations.DarajaOperation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="money_request",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.requester_id} {self.amount} → {self.destination} ({self.status})"

    @property
    def is_viewed(self) -> bool:
        return self.viewed_at is not None

    @property
    def status_badge_class(self) -> str:
        if self.status == self.Status.PENDING and self.is_viewed:
            return "pending-viewed"
        return str(self.status or "").lower()

    def mark_viewed(self, user) -> bool:
        """Record that a reviewer opened this request. Does not change status."""
        if self.status != self.Status.PENDING or self.viewed_at is not None:
            return False
        from django.utils import timezone

        self.viewed_at = timezone.now()
        self.viewed_by = user if getattr(user, "is_authenticated", False) else None
        self.save(update_fields=["viewed_at", "viewed_by", "updated_at"])
        return True


class CollectionMonitor(models.Model):
    """Paybill, till, or phone account tracked for ledger collections and live float."""

    class AccountType(models.TextChoices):
        PAYBILL = "PAYBILL", "Paybill"
        TILL = "TILL", "Till"
        PHONE = "PHONE", "Phone number"

    collection_code = models.CharField(
        max_length=12,
        unique=True,
        blank=True,
        help_text="Unique STK/C2B reference for this account (auto-generated).",
    )
    label = models.CharField(max_length=160)
    account_type = models.CharField(max_length=12, choices=AccountType.choices)
    identifier = models.CharField(max_length=20, help_text="Paybill, till, or MSISDN (254…).")
    account_ref = models.CharField(
        max_length=64,
        blank=True,
        help_text="Optional paybill account number for ledger filtering.",
    )
    paybill_account = models.ForeignKey(
        PaybillAccount,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="collection_monitors",
    )
    auto_refresh = models.BooleanField(
        default=True,
        help_text="Periodically request live balance from Safaricom when Daraja balance is configured.",
    )
    use_hub_daraja = models.BooleanField(
        default=True,
        help_text="Use hub Daraja STK credentials; turn off to paste this account's own consumer key/secret.",
    )
    daraja_consumer_key = models.CharField(max_length=255, blank=True)
    daraja_consumer_secret = models.CharField(max_length=512, blank=True)
    daraja_passkey = models.CharField(max_length=512, blank=True)
    daraja_shortcode = models.CharField(
        max_length=20,
        blank=True,
        help_text="Lipa shortcode for STK password when this account uses its own Daraja app.",
    )
    auto_payout_enabled = models.BooleanField(
        default=False,
        help_text="When on, each completed inbound collection is sent to the client phone via B2C.",
    )
    auto_payout_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Client M-Pesa number (07… or 254…) to receive automated transfers.",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="collection_monitors",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label", "identifier"]
        constraints = [
            models.UniqueConstraint(
                fields=("account_type", "identifier", "account_ref"),
                name="uniq_collection_monitor_target",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.get_account_type_display()} {self.identifier})"

    def daraja_identifier_type(self) -> str:
        if self.account_type == self.AccountType.PHONE:
            return "1"
        if self.account_type == self.AccountType.TILL:
            return "2"
        return "4"

    def normalized_phone(self) -> str:
        if self.account_type != self.AccountType.PHONE:
            return ""
        try:
            from integrations.daraja_client import kenya_msisdn

            return kenya_msisdn(self.identifier)
        except Exception:
            return (self.identifier or "").strip()

    def daraja_party_a(self) -> str:
        if self.account_type == self.AccountType.PHONE:
            return self.normalized_phone()
        return (self.identifier or "").strip()

    def display_identifier(self) -> str:
        if self.account_type == self.AccountType.PHONE and self.identifier.startswith("254"):
            local = "0" + self.identifier[3:]
            return local
        return self.identifier

    def save(self, *args, **kwargs):
        if not (self.collection_code or "").strip():
            self.collection_code = generate_collection_code()
        super().save(*args, **kwargs)

    def stk_account_reference(self) -> str:
        return (self.collection_code or "")[:12]

    def effective_daraja_value(self, field: str, *, hub_default: str = "") -> str:
        """Hub Daraja value unless this account overrides its own STK app credentials."""
        if not self.use_hub_daraja:
            own = (getattr(self, f"daraja_{field}", "") or "").strip()
            if own:
                return own
        return (hub_default or "").strip()

    def stk_transaction_type(self) -> str:
        if self.account_type == self.AccountType.TILL:
            return "CustomerBuyGoodsOnline"
        return "CustomerPayBillOnline"

    def stk_party_b(self) -> str:
        """Paybill or till that receives the STK payment (PartyB)."""
        if self.account_type == self.AccountType.PHONE:
            from integrations.models import DarajaConfig

            config = DarajaConfig.load()
            return self.effective_daraja_value("shortcode", hub_default=config.shortcode or "")
        return (self.identifier or "").strip()

    def ensure_ledger_paybill_account(self):
        """Link a ledger paybill row so successful STK/C2B posts show under this monitor."""
        if self.paybill_account_id:
            return self.paybill_account
        from integrations.models import DarajaConfig

        account = None
        if self.account_type in (self.AccountType.PAYBILL, self.AccountType.TILL):
            from paybill.automation import ensure_paybill_account

            account = ensure_paybill_account(label=self.label, paybill_number=self.identifier)
        else:
            config = DarajaConfig.load()
            if config.paybill_account_id:
                account = config.paybill_account
            elif (config.shortcode or "").strip():
                from paybill.automation import ensure_paybill_account

                account = ensure_paybill_account(
                    label=self.label or "Collections",
                    paybill_number=config.shortcode.strip(),
                )
        if account is not None:
            self.paybill_account = account
            self.save(update_fields=["paybill_account", "updated_at"])
        return account

    def stk_ready(self) -> bool:
        from integrations.models import DarajaConfig

        config = DarajaConfig.load()
        shortcode = self.effective_daraja_value("shortcode", hub_default=config.shortcode or "")
        passkey = self.effective_daraja_value("passkey", hub_default=config.passkey or "")
        key = self.effective_daraja_value("consumer_key", hub_default=config.consumer_key or "")
        secret = self.effective_daraja_value("consumer_secret", hub_default=config.consumer_secret or "")
        party_b = (self.stk_party_b() or "").strip()
        return bool(shortcode and passkey and key and secret and config.stk_callback_url and party_b)

    def has_own_daraja_credentials(self) -> bool:
        return not self.use_hub_daraja and bool(
            (self.daraja_consumer_key or "").strip() and (self.daraja_consumer_secret or "").strip()
        )


class CollectionMonitorCredential(models.Model):
    """API key used to trigger STK collection for one automation account."""

    monitor = models.ForeignKey(
        CollectionMonitor,
        on_delete=models.CASCADE,
        related_name="credentials",
    )
    name = models.CharField(max_length=80, default="primary")
    key_prefix = models.CharField(max_length=12)
    key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.monitor.collection_code}:{self.key_prefix}…"

    @classmethod
    def issue(cls, monitor: CollectionMonitor, name: str = "primary") -> tuple["CollectionMonitorCredential", str]:
        raw = "cm_" + secrets.token_urlsafe(32)
        cred = cls.objects.create(
            monitor=monitor,
            name=name,
            key_prefix=raw[:10],
            key_hash=hash_collection_api_key(raw),
        )
        return cred, raw

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

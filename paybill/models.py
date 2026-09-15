from django.conf import settings
from django.db import models


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

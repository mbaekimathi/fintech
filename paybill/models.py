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

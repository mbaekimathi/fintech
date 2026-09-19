from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        MONEY_REQUEST = "MONEY_REQUEST", "Money request"
        MONEY_REQUEST_RESULT = "MONEY_REQUEST_RESULT", "Money request update"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications_sent",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=255, blank=True)
    money_request = models.ForeignKey(
        "paybill.MoneyRequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.recipient_id}: {self.title}"

    @property
    def can_review(self) -> bool:
        return (
            self.kind == self.Kind.MONEY_REQUEST
            and self.money_request_id is not None
            and self.money_request is not None
            and self.money_request.status == self.money_request.Status.PENDING
        )

    def target_url_name(self) -> str:
        if self.kind == self.Kind.MONEY_REQUEST:
            return "paybill:transactions"
        return "core:dashboard"


class AppSettings(models.Model):
    """Hub-wide toggles (singleton row)."""

    app_approval_required = models.BooleanField(
        default=False,
        help_text="When on, approvers must enter their separate 6-digit approval password in the app before a payment is sent.",
    )
    stk_pin_approval_required = models.BooleanField(
        default=False,
        help_text="When on, approvers must complete an M-Pesa STK PIN prompt on their phone before a payment is sent.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "App settings"
        verbose_name_plural = "App settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls) -> "AppSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class PushSubscription(models.Model):
    """Browser Web Push subscription for phone/desktop tray alerts."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.TextField()
    endpoint_hash = models.CharField(max_length=64, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user_id} push"

    def as_subscription_info(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

    @staticmethod
    def hash_endpoint(endpoint: str) -> str:
        import hashlib

        return hashlib.sha256((endpoint or "").encode("utf-8")).hexdigest()

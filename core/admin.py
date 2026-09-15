from django.contrib import admin

from core.models import Notification, PushSubscription


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    search_fields = ("title", "body", "recipient__staff_code", "recipient__email")
    readonly_fields = ("created_at",)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "endpoint", "updated_at")
    search_fields = ("user__staff_code", "user__email", "endpoint")
    readonly_fields = ("created_at", "updated_at")

from django.contrib import admin

from integrations.models import APICredential, DarajaConfig


@admin.register(APICredential)
class APICredentialAdmin(admin.ModelAdmin):
    list_display = ("system", "name", "key_prefix", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active",)
    readonly_fields = ("key_prefix", "key_hash", "last_used_at", "created_at")


@admin.register(DarajaConfig)
class DarajaConfigAdmin(admin.ModelAdmin):
    list_display = (
        "environment",
        "shortcode",
        "paybill_account",
        "stk_transaction_type",
        "b2c_enabled",
        "b2b_enabled",
        "agent_shop_enabled",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at",)

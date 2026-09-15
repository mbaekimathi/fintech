from django.contrib import admin

from paybill.models import ConnectedSystem, LedgerEntry, MoneyRequest, PaybillAccount


@admin.register(ConnectedSystem)
class ConnectedSystemAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(PaybillAccount)
class PaybillAccountAdmin(admin.ModelAdmin):
    list_display = ("account_name", "paybill_number", "provider", "connected_system", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("account_name", "paybill_number")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "mpesa_reference",
        "payer_name",
        "expense_category",
        "amount",
        "currency",
        "status",
        "paybill_account",
        "posted_at",
    )
    list_filter = ("status", "direction", "currency", "expense_category")
    search_fields = (
        "reference",
        "mpesa_reference",
        "payer_phone",
        "payer_name",
        "account_ref",
        "expense_category",
        "expense_reason",
    )
    readonly_fields = ("posted_at",)
    raw_id_fields = ("money_request",)


@admin.register(MoneyRequest)
class MoneyRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "requester",
        "category",
        "destination_type",
        "destination",
        "amount",
        "status",
        "mpesa_reference",
        "created_at",
    )
    list_filter = ("status", "category", "destination_type")
    search_fields = (
        "destination",
        "account_ref",
        "reason",
        "mpesa_reference",
        "requester__staff_code",
    )
    readonly_fields = ("created_at", "updated_at")

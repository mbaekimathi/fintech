from django.contrib import admin

from paybill.models import ConnectedSystem, LedgerEntry, PaybillAccount


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
    list_display = ("reference", "amount", "currency", "status", "paybill_account", "posted_at")
    list_filter = ("status", "direction", "currency")
    search_fields = ("reference", "payer_phone", "account_ref", "payer_name")
    readonly_fields = ("posted_at",)

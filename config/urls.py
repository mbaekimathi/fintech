from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "NEXUS Ledger administration"
admin.site.site_title = "NEXUS Ledger"
admin.site.index_title = "Control plane"

handler403 = "django.views.defaults.permission_denied"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("paybill/", include("paybill.urls")),
    path("api/v1/", include("integrations.urls")),
]

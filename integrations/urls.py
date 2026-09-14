from django.urls import path

from integrations import views

app_name = "integrations"

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("ledger/", views.LedgerListView.as_view(), name="ledger-list"),
    path("ledger/ingest/", views.LedgerIngestView.as_view(), name="ledger-ingest"),
    path("paybills/", views.PaybillCatalogView.as_view(), name="paybill-catalog"),
    path("daraja/stk/callback/", views.DarajaStkCallbackView.as_view(), name="daraja-stk-callback"),
    path("daraja/result/", views.DarajaResultView.as_view(), name="daraja-result"),
    path("daraja/timeout/", views.DarajaTimeoutView.as_view(), name="daraja-timeout"),
]

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
    path(
        "daraja/agent/deposit/callback/",
        views.DarajaAgentCallbackView.as_view(),
        name="daraja-agent-deposit-callback",
    ),
    path(
        "daraja/agent/withdraw/callback/",
        views.DarajaAgentCallbackView.as_view(),
        name="daraja-agent-withdraw-callback",
    ),
    path("daraja/agent/result/", views.DarajaAgentCallbackView.as_view(), name="daraja-agent-result"),
    path("daraja/agent/timeout/", views.DarajaAgentCallbackView.as_view(), name="daraja-agent-timeout"),
]

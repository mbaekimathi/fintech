from django.urls import path

from core.views import (
    DashboardView,
    DarajaAgentShopSetupView,
    DarajaB2BSetupView,
    DarajaB2CSetupView,
    DarajaBalanceSetupView,
    DarajaSetupView,
    DarajaStkSetupView,
    DarajaTestView,
    DestinationLookupView,
    NotificationMarkReadView,
    NotificationOpenView,
    NotificationReviewView,
    PushSubscribeView,
    ServiceWorkerView,
    SettingsView,
    WebManifestView,
)

app_name = "core"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path(
        "money-requests/lookup/",
        DestinationLookupView.as_view(),
        name="destination-lookup",
    ),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings/daraja/", DarajaSetupView.as_view(), name="daraja"),
    path("settings/daraja/stk/", DarajaStkSetupView.as_view(), name="daraja-stk"),
    path("settings/daraja/balance/", DarajaBalanceSetupView.as_view(), name="daraja-balance"),
    path("settings/daraja/b2c/", DarajaB2CSetupView.as_view(), name="daraja-b2c"),
    path("settings/daraja/b2b/", DarajaB2BSetupView.as_view(), name="daraja-b2b"),
    path("settings/daraja/agent/", DarajaAgentShopSetupView.as_view(), name="daraja-agent"),
    path("settings/daraja/test/", DarajaTestView.as_view(), name="daraja-test"),
    path("notifications/read/", NotificationMarkReadView.as_view(), name="notifications-read"),
    path(
        "notifications/<int:pk>/open/",
        NotificationOpenView.as_view(),
        name="notification-open",
    ),
    path(
        "notifications/<int:pk>/review/",
        NotificationReviewView.as_view(),
        name="notification-review",
    ),
    path("notifications/push/", PushSubscribeView.as_view(), name="push-subscribe"),
    path("sw.js", ServiceWorkerView.as_view(), name="service-worker"),
    path("manifest.webmanifest", WebManifestView.as_view(), name="web-manifest"),
]

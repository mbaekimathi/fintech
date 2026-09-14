from django.urls import path

from core.views import DashboardView, DarajaSetupView, DarajaTestView, SettingsView

app_name = "core"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings/daraja/", DarajaSetupView.as_view(), name="daraja"),
    path("settings/daraja/test/", DarajaTestView.as_view(), name="daraja-test"),
]

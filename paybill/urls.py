from django.urls import path

from paybill import views

app_name = "paybill"

urlpatterns = [
    path("automations/", views.AutomationsView.as_view(), name="automations"),
    path(
        "automations/account/<int:pk>/",
        views.AutomationAccountView.as_view(),
        name="automation-account",
    ),
    path("transactions/", views.TransactionListView.as_view(), name="transactions"),
    path(
        "transactions/requests/<int:pk>/",
        views.MoneyRequestReviewView.as_view(),
        name="money-request-review",
    ),
    path(
        "transactions/requests/<int:pk>/reprompt/",
        views.MoneyRequestRepromptView.as_view(),
        name="money-request-reprompt",
    ),
]

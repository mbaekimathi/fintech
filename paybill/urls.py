from django.urls import path

from paybill import views

app_name = "paybill"

urlpatterns = [
    path("accounts/", views.PaybillAccountListView.as_view(), name="accounts"),
    path("transactions/", views.TransactionListView.as_view(), name="transactions"),
    path(
        "transactions/requests/<int:pk>/",
        views.MoneyRequestReviewView.as_view(),
        name="money-request-review",
    ),
    path("systems/", views.ConnectedSystemListView.as_view(), name="systems"),
]

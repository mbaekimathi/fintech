from django.db.models import Sum
from django.views.generic import ListView

from accounts.mixins import RoleRequiredMixin
from accounts.models import User
from paybill.models import ConnectedSystem, LedgerEntry, PaybillAccount


class PaybillAccountListView(RoleRequiredMixin, ListView):
    template_name = "paybill/accounts.html"
    context_object_name = "accounts"
    allowed_roles = (
        User.Role.ADMIN,
        User.Role.MANAGER,
        User.Role.ACCOUNTS,
        User.Role.IT_SUPPORT,
    )

    def get_queryset(self):
        return PaybillAccount.objects.select_related("connected_system")


class TransactionListView(RoleRequiredMixin, ListView):
    template_name = "paybill/transactions.html"
    context_object_name = "entries"
    paginate_by = 30
    allowed_roles = (
        User.Role.ADMIN,
        User.Role.MANAGER,
        User.Role.ACCOUNTS,
        User.Role.EMPLOYEE,
        User.Role.CLIENT,
        User.Role.IT_SUPPORT,
    )

    def get_queryset(self):
        qs = LedgerEntry.objects.select_related("paybill_account", "connected_system")
        user = self.request.user
        if user.role == User.Role.CLIENT:
            qs = qs.filter(account_ref=user.staff_code)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        totals = self.get_queryset().filter(status=LedgerEntry.Status.COMPLETED).aggregate(
            volume=Sum("amount")
        )
        context["volume"] = totals["volume"] or 0
        return context


class ConnectedSystemListView(RoleRequiredMixin, ListView):
    template_name = "paybill/systems.html"
    context_object_name = "systems"
    allowed_roles = (
        User.Role.ADMIN,
        User.Role.MANAGER,
        User.Role.IT_SUPPORT,
        User.Role.ACCOUNTS,
    )

    def get_queryset(self):
        return ConnectedSystem.objects.all()

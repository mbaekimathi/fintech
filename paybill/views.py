from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from accounts.mixins import RoleRequiredMixin
from accounts.models import User
from core.notifications import (
    mark_money_request_notifications_read,
    notify_money_request_result,
)
from integrations.daraja_client import DarajaError
from integrations.models import DarajaOperation
from paybill.models import ConnectedSystem, LedgerEntry, MoneyRequest, PaybillAccount
from paybill.services import (
    approve_and_transfer,
    money_request_by_ledger_reference,
    reject_money_request,
)

PENDING_REVIEW_ROLES = (
    User.Role.ADMIN,
    User.Role.MANAGER,
    User.Role.ACCOUNTS,
    User.Role.IT_SUPPORT,
)


def _annotate_ledger_entry(entry: LedgerEntry, lookup: dict[str, MoneyRequest]) -> LedgerEntry:
    """Attach initiator / category / reason for template display."""
    money_request = entry.money_request
    if money_request is None:
        money_request = lookup.get(entry.reference) or lookup.get(entry.mpesa_reference or "")
        if money_request is None and entry.reference.startswith("MR-"):
            money_request = lookup.get(entry.reference.rsplit("-OP-", 1)[0])
    meta = (entry.raw_payload or {}).get("_money_request") or {}
    if money_request is not None:
        requester = money_request.requester
        entry.initiator_name = requester.get_full_name() or requester.staff_code
        entry.initiator_code = requester.staff_code
        entry.expense_category = money_request.get_category_display()
        entry.expense_reason = money_request.reason
        entry.destination_label = money_request.get_destination_type_display()
        entry.destination_value = money_request.destination
        entry.destination_account_ref = money_request.account_ref or ""
        entry.source_paybill_number = money_request.source_paybill.paybill_number
    elif entry.expense_category or meta:
        entry.initiator_name = entry.payer_name or meta.get("initiator") or ""
        entry.initiator_code = meta.get("initiator_code") or ""
        entry.expense_category = entry.expense_category or meta.get("category_label") or ""
        entry.expense_reason = entry.expense_reason or meta.get("reason") or ""
        entry.destination_label = ""
        entry.destination_value = entry.payer_phone or meta.get("destination") or ""
        entry.destination_account_ref = entry.account_ref or meta.get("account_ref") or ""
        entry.source_paybill_number = entry.paybill_account.paybill_number
    else:
        entry.initiator_name = entry.payer_name or ""
        entry.initiator_code = ""
        entry.expense_category = ""
        entry.expense_reason = ""
        entry.destination_label = ""
        entry.destination_value = entry.payer_phone or ""
        entry.destination_account_ref = entry.account_ref or ""
        entry.source_paybill_number = entry.paybill_account.paybill_number
    return entry


class PaybillAccountListView(RoleRequiredMixin, ListView):
    template_name = "paybill/accounts.html"
    context_object_name = "accounts"
    required_activity = "manage_ledger"

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
        qs = LedgerEntry.objects.select_related(
            "paybill_account",
            "connected_system",
            "money_request",
            "money_request__requester",
            "money_request__source_paybill",
        )
        user = self.request.user
        if user.effective_role == User.Role.CLIENT:
            qs = qs.filter(account_ref=user.staff_code)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        totals = self.get_queryset().filter(status=LedgerEntry.Status.COMPLETED).aggregate(
            volume=Sum("amount")
        )
        context["volume"] = totals["volume"] or 0
        lookup = money_request_by_ledger_reference()
        for entry in context["entries"]:
            _annotate_ledger_entry(entry, lookup)
        role = self.request.user.effective_role
        can_review = self.request.user.can_review_requests()
        context["can_review_requests"] = can_review
        if can_review:
            context["pending_requests"] = (
                MoneyRequest.objects.filter(status=MoneyRequest.Status.PENDING)
                .select_related("requester", "source_paybill")
            )
            context["show_pending_requests"] = True
        elif role == User.Role.EMPLOYEE:
            context["pending_requests"] = (
                MoneyRequest.objects.filter(
                    status=MoneyRequest.Status.PENDING,
                    requester=self.request.user,
                ).select_related("requester", "source_paybill")
            )
            context["show_pending_requests"] = True
        else:
            context["pending_requests"] = MoneyRequest.objects.none()
            context["show_pending_requests"] = False
        return context


class MoneyRequestReviewView(RoleRequiredMixin, View):
    required_activity = "review_requests"

    def post(self, request, pk, *args, **kwargs):
        money_request = get_object_or_404(MoneyRequest, pk=pk)
        intent = (request.POST.get("intent") or "").strip().lower()
        next_url = reverse("paybill:transactions")

        if money_request.status != MoneyRequest.Status.PENDING:
            messages.error(request, "That request is no longer pending.")
            return redirect(next_url)

        if intent == "reject":
            reject_money_request(request, money_request)
            mark_money_request_notifications_read(money_request)
            notify_money_request_result(money_request, actor=request.user)
            messages.success(request, "Money request rejected.")
            return redirect(next_url)

        if intent != "approve":
            messages.error(request, "Choose approve or reject.")
            return redirect(next_url)

        from core.approval import approval_pin_ok

        if not approval_pin_ok(request, next_url=next_url):
            return redirect(next_url)

        try:
            money_request, operation = approve_and_transfer(request, money_request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(next_url)
        except DarajaError as exc:
            messages.error(request, str(exc))
            return redirect(next_url)

        mark_money_request_notifications_read(money_request)
        if money_request.status in {
            MoneyRequest.Status.PAID,
            MoneyRequest.Status.APPROVED,
            MoneyRequest.Status.FAILED,
        }:
            notify_money_request_result(money_request, actor=request.user)

        if money_request.status == MoneyRequest.Status.PAID:
            messages.success(
                request,
                operation.summary
                or f"Transfer of KES {money_request.amount} completed.",
            )
        elif operation.status == DarajaOperation.Status.QUEUED:
            messages.success(
                request,
                f"Approved. Transfer of KES {money_request.amount} queued with Safaricom.",
            )
        else:
            messages.error(
                request,
                operation.summary
                or operation.result_desc
                or "Transfer failed. Request marked as failed.",
            )
        return redirect(next_url)


class ConnectedSystemListView(RoleRequiredMixin, ListView):
    template_name = "paybill/systems.html"
    context_object_name = "systems"
    required_activity = "manage_ledger"

    def get_queryset(self):
        return ConnectedSystem.objects.all()

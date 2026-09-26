from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from accounts.mixins import RoleRequiredMixin
from accounts.models import User
from accounts.utils import write_audit
from core.notifications import (
    mark_money_request_notifications_read,
    notify_money_request_result,
    reprompt_money_request,
)
from integrations.daraja_client import DarajaError
from integrations.models import DarajaConfig, DarajaOperation
from integrations.c2b import (
    c2b_callback_urls,
    c2b_public_ready,
    c2b_shortcodes_to_register,
    register_c2b_urls,
    simulate_c2b_payment,
)
from paybill.automation import (
    collection_integration_copy,
    collection_stk_api_url,
    ensure_paybill_account,
    hub_company_snapshot,
    monitor_ledger_queryset,
    monitor_ledger_totals,
    request_monitor_balance,
    serialize_collection_monitor,
    serialize_collection_monitor_summary,
)
from paybill.c2b_forms import C2bSimulateForm
from paybill.forms import CollectionMonitorForm, CollectionMonitorPayoutForm
from paybill.collection_stk import initiate_monitor_stk_collection
from paybill.models import CollectionMonitor, CollectionMonitorCredential, LedgerEntry, MoneyRequest
from paybill.services import (
    approve_and_transfer,
    flash_money_request_transfer_result,
    money_request_by_ledger_reference,
    redirect_after_transfer,
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
        context["can_reprompt_pending"] = (
            not can_review and self.request.user.can_submit_requests()
        )
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
            return redirect_after_transfer(request, next_url)

        if intent == "reject":
            reject_money_request(request, money_request)
            mark_money_request_notifications_read(money_request)
            notify_money_request_result(money_request, actor=request.user)
            messages.success(request, "Money request rejected.")
            return redirect_after_transfer(request, next_url)

        if intent != "approve":
            messages.error(request, "Choose approve or reject.")
            return redirect_after_transfer(request, next_url)

        from core.approval import approval_ok

        if not approval_ok(request, money_request=money_request, next_url=next_url):
            return redirect_after_transfer(request, next_url)

        try:
            money_request, operation = approve_and_transfer(request, money_request)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect_after_transfer(request, next_url)
        except DarajaError as exc:
            messages.error(request, str(exc))
            return redirect_after_transfer(request, next_url)

        mark_money_request_notifications_read(money_request)
        if money_request.status in {
            MoneyRequest.Status.PAID,
            MoneyRequest.Status.APPROVED,
            MoneyRequest.Status.FAILED,
        }:
            notify_money_request_result(money_request, actor=request.user)

        flash_money_request_transfer_result(request, money_request, operation)
        return redirect_after_transfer(request, next_url)


class MoneyRequestRepromptView(RoleRequiredMixin, View):
    allowed_roles = (User.Role.EMPLOYEE,)

    def post(self, request, pk, *args, **kwargs):
        if not request.user.can_submit_requests():
            messages.error(request, "You are not allowed to reprompt money requests.")
            return redirect("paybill:transactions")

        money_request = get_object_or_404(
            MoneyRequest,
            pk=pk,
            requester=request.user,
        )
        if money_request.status != MoneyRequest.Status.PENDING:
            messages.error(request, "That request is no longer pending.")
            return redirect("paybill:transactions")

        count = reprompt_money_request(money_request)
        write_audit(
            request,
            "money_request.reprompt",
            object_type="money_request",
            object_id=money_request.pk,
            detail={
                "amount": str(money_request.amount),
                "destination": money_request.destination,
                "reviewers_notified": count,
            },
        )
        if count:
            messages.success(
                request,
                f"Approvers notified again for KES {money_request.amount:,.2f}.",
            )
        else:
            messages.warning(request, "No approvers were available to notify.")
        return redirect("paybill:transactions")


class CollectionAutomationMixin:
    required_activity = "manage_ledger"

    def _monitors(self):
        return CollectionMonitor.objects.filter(is_active=True).select_related("paybill_account")

    def _wants_json(self, request) -> bool:
        return (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )

    def _pop_api_key_session(self, request):
        new_api_key = request.session.pop("new_collection_api_key", "")
        new_api_monitor_id = request.session.pop("new_collection_api_monitor_id", None)
        new_api_monitor_label = ""
        new_api_integration_copy = ""
        if new_api_key and new_api_monitor_id:
            key_monitor = CollectionMonitor.objects.filter(pk=new_api_monitor_id).first()
            if key_monitor:
                new_api_monitor_label = key_monitor.label
                new_api_integration_copy = collection_integration_copy(
                    key_monitor,
                    stk_url=collection_stk_api_url(request),
                    api_key=new_api_key,
                )
        return {
            "new_collection_api_key": new_api_key,
            "new_collection_api_monitor_id": new_api_monitor_id,
            "new_api_monitor_label": new_api_monitor_label,
            "new_api_integration_copy": new_api_integration_copy,
        }

    def _hub_c2b_context(self, request, *, config: DarajaConfig):
        c2b_ready, c2b_detail = c2b_public_ready(request)
        c2b_urls = c2b_callback_urls(request)
        return {
            "c2b_ready": c2b_ready,
            "c2b_detail": c2b_detail,
            "c2b_validation_url": c2b_urls.get("validation_url", ""),
            "c2b_confirmation_url": c2b_urls.get("confirmation_url", ""),
            "c2b_shortcodes": c2b_shortcodes_to_register(),
            "c2b_registration_log": config.c2b_registration_log,
            "c2b_sandbox": str(config.environment) == DarajaConfig.Environment.SANDBOX,
        }

    def _hub_list_context(self, request, *, form=None):
        config = DarajaConfig.load()
        monitors = list(self._monitors())
        accounts = [serialize_collection_monitor_summary(row, config=config) for row in monitors]
        total_collected = sum(Decimal(a["collected_total"]) for a in accounts)
        ctx = {
            "form": form or CollectionMonitorForm(),
            "simulate_form": C2bSimulateForm(),
            "company": hub_company_snapshot(config=config),
            "accounts": accounts,
            "accounts_count": len(accounts),
            "stk_ready_count": sum(1 for a in accounts if a.get("stk_ready")),
            "total_collected": total_collected,
            "balance_ready": config.balance_ready,
            **self._hub_c2b_context(request, config=config),
        }
        return ctx


class AutomationsView(CollectionAutomationMixin, RoleRequiredMixin, View):
    """Hub: company Daraja snapshot and list of collection accounts."""

    template_name = "paybill/automations.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._hub_list_context(request))

    def post(self, request, *args, **kwargs):
        intent = (request.POST.get("intent") or "").strip().lower()
        wants_json = self._wants_json(request)

        if intent == "create":
            form = CollectionMonitorForm(request.POST)
            if not form.is_valid():
                if wants_json:
                    return JsonResponse(
                        {"ok": False, "errors": form.errors.get_json_data()},
                        status=400,
                    )
                messages.error(request, "Fix the highlighted fields and try again.")
                ctx = self._hub_list_context(request, form=form)
                ctx["register_open"] = True
                return render(request, self.template_name, ctx)

            monitor = form.save(commit=False)
            monitor.created_by = request.user
            if monitor.account_type in (
                CollectionMonitor.AccountType.PAYBILL,
                CollectionMonitor.AccountType.TILL,
            ):
                monitor.paybill_account = ensure_paybill_account(
                    label=monitor.label,
                    paybill_number=monitor.identifier,
                )
            monitor.save()
            monitor.ensure_ledger_paybill_account()
            _cred, raw_key = CollectionMonitorCredential.issue(monitor)
            request.session["new_collection_api_key"] = raw_key
            request.session["new_collection_api_monitor_id"] = monitor.pk
            write_audit(
                request,
                "automation.monitor.created",
                object_type="collection_monitor",
                object_id=monitor.pk,
                detail={
                    "type": monitor.account_type,
                    "identifier": monitor.identifier,
                    "collection_code": monitor.collection_code,
                },
            )
            if wants_json:
                config = DarajaConfig.load()
                return JsonResponse(
                    {
                        "ok": True,
                        "account": serialize_collection_monitor(monitor, config=config, request=request),
                    }
                )
            messages.success(
                request,
                f"Added {monitor.label}. Copy the new API key on the account page.",
            )
            return redirect("paybill:automation-account", pk=monitor.pk)

        if intent == "register-c2b":
            try:
                lines = register_c2b_urls(request=request)
            except DarajaError as exc:
                if wants_json:
                    return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
                messages.error(request, str(exc))
                return redirect("paybill:automations")
            detail = " ".join(lines)
            if wants_json:
                return JsonResponse({"ok": True, "detail": detail, "lines": lines})
            messages.success(request, f"C2B URLs registered: {detail}")
            return redirect("paybill:automations")

        if intent == "simulate-c2b":
            sim_form = C2bSimulateForm(request.POST)
            if not sim_form.is_valid():
                messages.error(request, "Fix the sandbox simulation fields.")
                return redirect("paybill:automations")
            try:
                body = simulate_c2b_payment(
                    shortcode=sim_form.cleaned_data["shortcode"],
                    amount=sim_form.cleaned_data["amount"],
                    bill_ref=sim_form.cleaned_data.get("bill_ref") or "NEXUS",
                    msisdn=sim_form.cleaned_data["msisdn"],
                    command_id=sim_form.cleaned_data["command_id"],
                )
            except DarajaError as exc:
                messages.error(request, str(exc))
                return redirect("paybill:automations")
            desc = body.get("ResponseDescription") or body.get("CustomerMessage") or "Simulated"
            messages.success(
                request,
                f"Sandbox C2B simulated. {desc} Confirmation should hit your ledger shortly.",
            )
            return redirect("paybill:automations")

        if wants_json:
            return JsonResponse({"ok": False, "detail": "Unknown action."}, status=400)
        messages.error(request, "Unknown action.")
        return redirect("paybill:automations")


class AutomationAccountView(CollectionAutomationMixin, RoleRequiredMixin, View):
    """Single collection account: STK, API keys, balance, integration."""

    template_name = "paybill/automation_account.html"

    @staticmethod
    def _local_phone_display(raw: str) -> str:
        phone = (raw or "").strip()
        if phone.startswith("254") and len(phone) == 12:
            return "0" + phone[3:]
        return phone

    def _payout_form(self, monitor: CollectionMonitor) -> CollectionMonitorPayoutForm:
        from paybill.auto_payout import monitor_payout_destination

        dest = monitor_payout_destination(monitor)
        if (
            monitor.auto_payout_destination_type == MoneyRequest.DestinationType.PHONE
            and dest.startswith("254")
            and len(dest) == 12
        ):
            dest = self._local_phone_display(dest)
        return CollectionMonitorPayoutForm(
            instance=monitor,
            initial={"auto_payout_destination": dest},
        )

    def _monitor(self, pk: int):
        return get_object_or_404(
            CollectionMonitor.objects.select_related("paybill_account"),
            pk=pk,
            is_active=True,
        )

    def get(self, request, pk, *args, **kwargs):
        monitor = self._monitor(pk)
        config = DarajaConfig.load()
        if request.GET.get("poll") == "balances":
            payload = {
                "ok": True,
                "balance_ready": bool(config.balance_ready),
                "accounts": [
                    serialize_collection_monitor(monitor, config=config, request=request),
                ],
            }
            return JsonResponse(payload)

        row = serialize_collection_monitor(monitor, config=config, request=request)
        api_ctx = self._pop_api_key_session(request)
        ledger_qs = monitor_ledger_queryset(monitor)
        paginator = Paginator(ledger_qs, 30)
        ledger_page = paginator.get_page(request.GET.get("page"))
        lookup = money_request_by_ledger_reference()
        ledger_entries = [_annotate_ledger_entry(entry, lookup) for entry in ledger_page.object_list]
        ledger_totals = monitor_ledger_totals(monitor)
        return render(
            request,
            self.template_name,
            {
                "monitor": monitor,
                "row": row,
                "balance_ready": config.balance_ready,
                "poll_url": reverse("paybill:automation-account", kwargs={"pk": pk}) + "?poll=balances",
                "post_url": reverse("paybill:automation-account", kwargs={"pk": pk}),
                "hub_url": reverse("paybill:automations"),
                "ledger_entries": ledger_entries,
                "ledger_page": ledger_page,
                "ledger_totals": ledger_totals,
                "payout_form": self._payout_form(monitor),
                "b2c_ready": config.b2c_ready,
                "b2b_ready": config.b2b_ready,
                **api_ctx,
            },
        )

    def post(self, request, pk, *args, **kwargs):
        monitor = self._monitor(pk)
        intent = (request.POST.get("intent") or "").strip().lower()
        wants_json = self._wants_json(request)
        account_url = reverse("paybill:automation-account", kwargs={"pk": pk})
        config = DarajaConfig.load()

        if intent == "save-payout":
            form = CollectionMonitorPayoutForm(request.POST, instance=monitor)
            if not form.is_valid():
                messages.error(request, "Fix the client payout fields.")
                return redirect(f"{account_url}#client-payout")
            form.save()
            write_audit(
                request,
                "collection_monitor.payout_config",
                object_type="collection_monitor",
                object_id=monitor.pk,
                detail={"auto_payout_enabled": monitor.auto_payout_enabled},
            )
            if monitor.auto_payout_enabled:
                messages.success(
                    request,
                    "Client auto-send is on — inbound collections will B2C to the configured phone.",
                )
            else:
                messages.success(request, "Client auto-send is off for this account.")
            return redirect(f"{account_url}#client-payout")

        if intent == "issue-credential":
            _cred, raw_key = CollectionMonitorCredential.issue(monitor)
            request.session["new_collection_api_key"] = raw_key
            request.session["new_collection_api_monitor_id"] = monitor.pk
            messages.success(
                request,
                f"New API key for {monitor.collection_code}. Copy it below — shown once.",
            )
            return redirect(account_url)

        if intent == "stk-collect":
            from integrations.daraja_client import kenya_msisdn

            phone_raw = (request.POST.get("phone") or "").strip()
            amount_raw = (request.POST.get("amount") or "").strip()
            if not phone_raw:
                messages.error(request, "Enter the payer's M-Pesa phone number.")
                return redirect(account_url)
            try:
                phone = kenya_msisdn(phone_raw)
            except DarajaError as exc:
                messages.error(request, str(exc))
                return redirect(account_url)
            try:
                amount = Decimal(amount_raw)
            except Exception:
                messages.error(request, "Enter a valid amount.")
                return redirect(account_url)
            if amount < 1:
                messages.error(request, "Amount must be at least KES 1.")
                return redirect(account_url)
            try:
                operation = initiate_monitor_stk_collection(
                    monitor=monitor,
                    phone=phone,
                    amount=amount,
                    request=request,
                    created_by=request.user,
                )
            except DarajaError as exc:
                messages.error(request, str(exc))
                return redirect(account_url)
            write_audit(
                request,
                "automation.stk.collect",
                object_type="daraja_operation",
                object_id=operation.pk,
                detail={
                    "monitor": monitor.collection_code,
                    "amount": str(amount),
                    "checkout": operation.checkout_request_id,
                },
            )
            messages.success(
                request,
                (
                    f"STK push sent for KES {amount:,.2f} — customer must enter M-Pesa PIN. "
                    f"After payment, collected total updates for collection ID {monitor.collection_code}."
                ),
            )
            return redirect(account_url)

        if intent == "remove":
            monitor.is_active = False
            monitor.save(update_fields=["is_active", "updated_at"])
            write_audit(
                request,
                "automation.monitor.removed",
                object_type="collection_monitor",
                object_id=monitor.pk,
            )
            if wants_json:
                return JsonResponse({"ok": True})
            messages.success(request, "Account removed from automations.")
            return redirect("paybill:automations")

        if intent == "refresh":
            config = DarajaConfig.load()
            if not config.balance_ready:
                detail = "Configure Daraja live balance (initiator + result URLs) first."
                if wants_json:
                    return JsonResponse({"ok": False, "detail": detail}, status=400)
                messages.error(request, detail)
                return redirect(account_url)
            try:
                request_monitor_balance(monitor=monitor, request=request, created_by=request.user)
            except DarajaError as exc:
                if wants_json:
                    return JsonResponse({"ok": False, "detail": str(exc)}, status=400)
                messages.error(request, str(exc))
                return redirect(account_url)
            config = DarajaConfig.load()
            payload = {
                "ok": True,
                "refreshed": 1,
                "accounts": [
                    serialize_collection_monitor(monitor, config=config, request=request),
                ],
            }
            if wants_json:
                return JsonResponse(payload)
            messages.success(request, "Live balance requested. Value updates when Safaricom responds.")
            return redirect(account_url)

        if wants_json:
            return JsonResponse({"ok": False, "detail": "Unknown action."}, status=400)
        messages.error(request, "Unknown action.")
        return redirect(account_url)


class AccountConfigurationView(CollectionAutomationMixin, RoleRequiredMixin, View):
    """Legacy URL — client payout is configured on each collection account page."""

    def get(self, request, *args, **kwargs):
        messages.info(
            request,
            "Open a collection account and use Client payout automation on that account’s page.",
        )
        return redirect("paybill:automations")

    def post(self, request, *args, **kwargs):
        return redirect("paybill:automations")

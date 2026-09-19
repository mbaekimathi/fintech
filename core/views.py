from django.contrib import messages
from django.conf import settings as django_settings
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, UpdateView

import json
from pathlib import Path

from accounts.mixins import ApprovedRequiredMixin, RoleRequiredMixin
from accounts.models import User
from accounts.utils import write_audit
from core.approval import approval_pin_ok
from core.models import AppSettings, PushSubscription
from core.notifications import (
    mark_money_request_notifications_read,
    mark_notification_read,
    notifications_for_session_user,
    notify_money_request_result,
    notify_money_request_submitted,
)
from integrations.callbacks import apply_stk_query, expire_stale_queues, wait_for_result
from integrations.daraja import (
    SANDBOX_B2B_DESTINATION,
    SANDBOX_TEST_AMOUNT,
    SANDBOX_TEST_PHONE,
    apply_sandbox_to_instance,
    callback_urls,
    capability_status,
    hub_balance_operation,
    panel_blockers,
    integration_status,
    request_hub_balance,
    sandbox_defaults_payload,
    serialize_hub_balance,
)
from integrations.daraja_client import DarajaClient, DarajaError
from integrations.forms import (
    SECRET_FIELDS,
    BalanceQueryForm,
    DarajaUnifiedForm,
    SendMoneyForm,
    StkPromptForm,
    UtilityTransferForm,
)
from integrations.models import DarajaConfig, DarajaOperation
from paybill.forms import MoneyRequestForm
from paybill.lookup import lookup_destination, resolve_recipient_name
from paybill.models import ConnectedSystem, LedgerEntry, MoneyRequest, PaybillAccount
from paybill.services import approve_and_transfer, mpesa_receipt_from_operation, reject_money_request


def _hub_paybill_account():
    config = DarajaConfig.load()
    if config.paybill_account_id:
        return config.paybill_account
    return PaybillAccount.objects.filter(is_active=True).order_by("id").first()


def _safe_next_url(request, fallback_name="core:dashboard"):
    candidate = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return reverse(fallback_name)


def _shows_hub_balance(user) -> bool:
    return user.can_view_hub_balance()


def _daraja_ack_fields(body: dict) -> dict:
    return {
        "merchant_request_id": body.get("MerchantRequestID") or "",
        "checkout_request_id": body.get("CheckoutRequestID") or "",
        "conversation_id": body.get("ConversationID") or "",
        "originator_conversation_id": body.get("OriginatorConversationID") or "",
        "result_desc": (body.get("ResponseDescription") or body.get("CustomerMessage") or "")[:255],
        "response_payload": body,
    }


def _redact_daraja_payload(payload: dict) -> dict:
    data = dict(payload or {})
    for key in ("SecurityCredential", "Password"):
        if key in data:
            data[key] = "[redacted]"
    return data


class DashboardView(ApprovedRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get(self, request, *args, **kwargs):
        if request.GET.get("poll") == "hub-balance" and _shows_hub_balance(request.user):
            expire_stale_queues()
            config = DarajaConfig.load()
            operation = hub_balance_operation(config)
            payload = serialize_hub_balance(config, operation)
            payload["ok"] = True
            return JsonResponse(payload)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        intent = (request.POST.get("intent") or "").strip()
        if intent == "hub-balance":
            return self._post_hub_balance(request)
        if intent == "utility-transfer":
            return self._post_utility_transfer(request)
        if not request.user.can_submit_requests():
            messages.error(request, "You are not allowed to submit money requests.")
            return redirect("core:dashboard")

        source = _hub_paybill_account()
        if not source:
            messages.error(request, "No paybill account is set up yet. Ask an admin to configure one.")
            return redirect("core:dashboard")

        form = MoneyRequestForm(request.POST)
        if form.is_valid():
            money_request = form.save(commit=False)
            money_request.requester = request.user
            money_request.source_paybill = source
            money_request.status = MoneyRequest.Status.PENDING
            money_request.recipient_name = resolve_recipient_name(
                destination_type=money_request.destination_type,
                destination=money_request.destination,
            )
            money_request.save()
            notify_money_request_submitted(money_request)
            write_audit(
                request,
                "money_request.create",
                object_type="money_request",
                object_id=money_request.pk,
                detail={
                    "amount": str(money_request.amount),
                    "category": money_request.category,
                    "destination_type": money_request.destination_type,
                    "destination": money_request.destination,
                    "recipient_name": money_request.recipient_name,
                },
            )
            messages.success(
                request,
                f"Request for KES {money_request.amount} submitted. Awaiting approval.",
            )
            return redirect("core:dashboard")

        context = self.get_context_data(money_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_employee = user.can_submit_requests()
        is_account_dashboard = _shows_hub_balance(user)
        context["is_employee_dashboard"] = is_employee and not is_account_dashboard
        if not is_employee and not is_account_dashboard:
            today = timezone.localdate()
            completed = LedgerEntry.objects.filter(status=LedgerEntry.Status.COMPLETED)
            today_qs = completed.filter(posted_at__date=today)
            context.update(
                {
                    "today_volume": today_qs.aggregate(total=Sum("amount"))["total"] or 0,
                    "today_count": today_qs.count(),
                    "system_count": ConnectedSystem.objects.filter(is_active=True).count(),
                    "paybill_count": PaybillAccount.objects.filter(is_active=True).count(),
                    "pending_people": User.objects.filter(is_active=True)
                    .filter(Q(is_approved=False) | Q(role=User.Role.PENDING_APPROVAL))
                    .count(),
                }
            )
        if is_employee and not is_account_dashboard:
            source = _hub_paybill_account()
            context["source_paybill"] = source
            if "money_form" not in context:
                context["money_form"] = MoneyRequestForm(
                    initial={"destination_type": MoneyRequest.DestinationType.PHONE}
                )
            mine = MoneyRequest.objects.filter(requester=user).select_related(
                "source_paybill", "daraja_operation"
            )
            context["pending_money_requests"] = mine.filter(
                status=MoneyRequest.Status.PENDING
            )[:12]
            approved_rows = list(
                mine.filter(
                    status__in=(
                        MoneyRequest.Status.APPROVED,
                        MoneyRequest.Status.PAID,
                        MoneyRequest.Status.FAILED,
                    )
                )[:12]
            )
            for row in approved_rows:
                row.mpesa_reference = (
                    str(row.mpesa_reference or "").strip()
                    or mpesa_receipt_from_operation(row.daraja_operation)
                )
            context["approved_money_requests"] = approved_rows
        elif is_account_dashboard:
            config = DarajaConfig.load()
            operation = hub_balance_operation(config)
            context["is_account_dashboard"] = True
            context["show_hub_balance"] = True
            context["hub_paybill"] = _hub_paybill_account()
            context["hub_balance"] = serialize_hub_balance(config, operation)
            context["utility_transfer_form"] = UtilityTransferForm()
        return context

    def _post_hub_balance(self, request):
        if not _shows_hub_balance(request.user):
            return JsonResponse(
                {"ok": False, "detail": "You cannot request live balance from this role."},
                status=403,
            )
        wants_json = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        config = DarajaConfig.load()
        snapshot = serialize_hub_balance(config)
        if not config.balance_ready:
            payload = {**snapshot, "ok": False, "detail": "Live balance is not configured yet."}
            if wants_json:
                return JsonResponse(payload, status=400)
            messages.error(request, payload["detail"])
            return redirect("core:dashboard")

        pending = hub_balance_operation(config, queued_only=True)
        if pending and pending.is_fresh_queue():
            payload = {**serialize_hub_balance(config, pending), "ok": True}
            if wants_json:
                return JsonResponse(payload)
            return redirect("core:dashboard")

        urls = callback_urls(request)
        try:
            operation = request_hub_balance(
                config=config,
                created_by=request.user,
                result_url=urls.get("result_url") or config.result_url,
                timeout_url=urls.get("timeout_url") or config.timeout_url,
            )
        except DarajaError as exc:
            payload = {**snapshot, "ok": False, "detail": str(exc)}
            if wants_json:
                return JsonResponse(payload, status=400)
            messages.error(request, str(exc))
            return redirect("core:dashboard")

        write_audit(
            request,
            "daraja.balance.sent",
            object_type="daraja_operation",
            object_id=operation.pk,
        )
        payload = {**serialize_hub_balance(config, operation), "ok": True}
        if wants_json:
            return JsonResponse(payload)
        messages.success(
            request,
            operation.summary or "Balance requested. This page updates when Safaricom responds.",
        )
        return redirect("core:dashboard")

    def _post_utility_transfer(self, request):
        if not _shows_hub_balance(request.user):
            return JsonResponse(
                {"ok": False, "detail": "You cannot move float from this role."},
                status=403,
            )
        wants_json = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        config = DarajaConfig.load()
        snapshot = serialize_hub_balance(config)
        if not config.b2b_enabled or not config.balance_ready:
            detail = "Internal float transfer is not configured yet. Turn on B2B and live balance on Daraja setup."
            payload = {**snapshot, "ok": False, "detail": detail}
            if wants_json:
                return JsonResponse(payload, status=400)
            messages.error(request, detail)
            return redirect("core:dashboard")

        form = UtilityTransferForm(request.POST)
        if not form.is_valid():
            detail = " ".join(
                error for errors in form.errors.values() for error in errors
            )
            payload = {**snapshot, "ok": False, "detail": detail or "Enter a valid amount."}
            if wants_json:
                return JsonResponse(payload, status=400)
            messages.error(request, payload["detail"])
            context = self.get_context_data(utility_transfer_form=form)
            return self.render_to_response(context)

        amount = form.cleaned_data["amount"]
        utility_amount = snapshot.get("utility_amount")
        if utility_amount is not None and amount > utility_amount:
            detail = f"Amount exceeds utility balance of KES {utility_amount}."
            payload = {**snapshot, "ok": False, "detail": detail}
            if wants_json:
                return JsonResponse(payload, status=400)
            messages.error(request, detail)
            context = self.get_context_data(utility_transfer_form=form)
            return self.render_to_response(context)

        urls = callback_urls(request)
        client = DarajaClient(config)
        try:
            body, payload_req, shortcode = client.utility_to_working(
                amount=amount,
                result_url=urls.get("result_url") or config.result_url,
                timeout_url=urls.get("timeout_url") or config.timeout_url,
            )
        except DarajaError as exc:
            payload = {**snapshot, "ok": False, "detail": str(exc)}
            if wants_json:
                return JsonResponse(payload, status=400)
            messages.error(request, str(exc))
            return redirect("core:dashboard")

        operation = DarajaOperation.objects.create(
            kind=DarajaOperation.Kind.B2B,
            destination=shortcode,
            amount=amount,
            account_ref="UTILITY-WORKING",
            request_payload=_redact_daraja_payload(payload_req),
            summary=body.get("ResponseDescription") or "Utility transfer queued.",
            created_by=request.user,
            **_daraja_ack_fields(body),
        )
        operation = wait_for_result(operation)
        write_audit(
            request,
            "daraja.utility_transfer.sent",
            object_type="daraja_operation",
            object_id=operation.pk,
            detail={"amount": str(amount), "shortcode": shortcode},
        )

        if operation.status == DarajaOperation.Status.SUCCESS:
            detail = operation.summary or f"Moved KES {amount} to working capital."
            messages.success(request, detail)
        elif operation.status == DarajaOperation.Status.FAILED:
            detail = operation.summary or operation.result_desc or "Utility transfer failed."
            messages.error(request, detail)
        elif operation.status == DarajaOperation.Status.TIMEOUT:
            detail = operation.summary or "Safaricom timed out. Check the transfer history below."
            messages.error(request, detail)
        else:
            detail = operation.summary or "Utility transfer queued with Safaricom."
            messages.success(request, detail)

        response_payload = {
            **serialize_hub_balance(config),
            "ok": operation.status != DarajaOperation.Status.FAILED,
            "detail": detail,
            "transfer": {
                "id": operation.pk,
                "status": operation.status,
                "status_label": operation.get_status_display(),
                "summary": operation.summary,
                "amount": str(amount),
            },
        }
        if wants_json:
            return JsonResponse(response_payload)
        return redirect("core:dashboard")


class DestinationLookupView(ApprovedRequiredMixin, View):
    """Live recipient / business-name check for the employee money-request form."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        if request.user.effective_role != User.Role.EMPLOYEE:
            return JsonResponse(
                {"ok": False, "found": False, "detail": "Only employees can look up destinations."},
                status=403,
            )
        payload = lookup_destination(
            destination_type=request.GET.get("destination_type") or "",
            destination=request.GET.get("destination") or "",
        )
        return JsonResponse(payload)


class NotificationMarkReadView(ApprovedRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        next_url = _safe_next_url(request)
        visible = notifications_for_session_user(request.user)
        if request.POST.get("intent") == "all":
            visible.filter(is_read=False).update(is_read=True)
            messages.success(request, "Notifications marked as read.")
            return redirect(next_url)
        pk = request.POST.get("notification_id")
        notification = get_object_or_404(visible, pk=pk)
        mark_notification_read(notification)
        return redirect(next_url)


class NotificationOpenView(ApprovedRequiredMixin, View):
    """Mark a notification read and open its related page."""

    def post(self, request, pk, *args, **kwargs):
        notification = get_object_or_404(
            notifications_for_session_user(request.user).select_related("money_request"),
            pk=pk,
        )
        mark_notification_read(notification)
        money_request = notification.money_request
        if money_request is not None:
            money_request.mark_viewed(request.user)
        return redirect(notification.target_url_name())


class NotificationReviewView(RoleRequiredMixin, View):
    required_activity = "review_requests"

    def post(self, request, pk, *args, **kwargs):
        notification = get_object_or_404(
            notifications_for_session_user(request.user).select_related("money_request"),
            pk=pk,
        )
        next_url = _safe_next_url(request)
        money_request = notification.money_request
        if money_request is None:
            messages.error(request, "That notification has no money request.")
            mark_notification_read(notification)
            return redirect(next_url)

        intent = (request.POST.get("intent") or "").strip().lower()
        if money_request.status != MoneyRequest.Status.PENDING:
            messages.error(request, "That request is no longer pending.")
            mark_money_request_notifications_read(money_request)
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


class ServiceWorkerView(View):
    """Root-scoped service worker for Web Push tray notifications."""

    def get(self, request, *args, **kwargs):
        path = Path(django_settings.BASE_DIR) / "static" / "sw.js"
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            body = "/* service worker missing */"
        response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
        response["Service-Worker-Allowed"] = "/"
        response["Cache-Control"] = "no-cache"
        return response


class WebManifestView(View):
    def get(self, request, *args, **kwargs):
        icon = request.build_absolute_uri("/static/icons/icon.svg")
        payload = {
            "name": "NEXUS Ledger",
            "short_name": "NEXUS",
            "description": "Paybill hub and money request approvals",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#0c1624",
            "theme_color": "#0c1624",
            "icons": [
                {
                    "src": icon,
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
        }
        return JsonResponse(payload)


class PushSubscribeView(ApprovedRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "detail": "Invalid JSON."}, status=400)
        endpoint = (payload.get("endpoint") or "").strip()
        keys = payload.get("keys") or {}
        p256dh = (keys.get("p256dh") or "").strip()
        auth = (keys.get("auth") or "").strip()
        if not endpoint or not p256dh or not auth:
            return JsonResponse({"ok": False, "detail": "Incomplete subscription."}, status=400)
        row, _created = PushSubscription.objects.update_or_create(
            endpoint_hash=PushSubscription.hash_endpoint(endpoint),
            defaults={
                "user": request.user,
                "endpoint": endpoint,
                "p256dh": p256dh[:200],
                "auth": auth[:100],
                "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:255],
            },
        )
        return JsonResponse({"ok": True, "id": row.pk})

    def delete(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        endpoint = (payload.get("endpoint") or "").strip()
        qs = PushSubscription.objects.filter(user=request.user)
        if endpoint:
            qs = qs.filter(endpoint=endpoint)
        deleted, _ = qs.delete()
        return JsonResponse({"ok": True, "deleted": deleted})


class SettingsView(ApprovedRequiredMixin, TemplateView):
    template_name = "core/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_hours = max(1, int(django_settings.SESSION_COOKIE_AGE / 3600))
        context.update(
            {
                "hub_timezone": django_settings.TIME_ZONE,
                "debug_enabled": django_settings.DEBUG,
                "session_hours": session_hours,
                "lockout_limit": getattr(django_settings, "AXES_FAILURE_LIMIT", 5),
            }
        )
        return context


class AppSettingsView(RoleRequiredMixin, TemplateView):
    template_name = "core/app_settings.html"
    required_activity = "manage_app_settings"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings = AppSettings.load()
        context["app_settings"] = settings
        context["pin_approval_required"] = settings.pin_approval_required
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.can_manage_app_settings() and not (
            request.user.is_superuser and not request.user.is_role_switched
        ):
            return JsonResponse({"ok": False, "detail": "Not allowed."}, status=403)

        settings = AppSettings.load()
        enabled = request.POST.get("pin_approval_required") in {"1", "true", "on"}
        settings.pin_approval_required = enabled
        settings.save(update_fields=["pin_approval_required", "updated_at"])
        write_audit(
            request,
            "app_settings.pin_approval",
            object_type="app_settings",
            object_id=settings.pk,
            detail={"pin_approval_required": enabled},
        )

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "pin_approval_required": settings.pin_approval_required})

        label = "enabled" if enabled else "disabled"
        messages.success(request, f"PIN approval prompting {label}.")
        return redirect("core:app-settings")


class DarajaSetupView(RoleRequiredMixin, UpdateView):
    template_name = "core/daraja.html"
    form_class = DarajaUnifiedForm
    success_url = reverse_lazy("core:daraja")
    context_object_name = "config"
    required_activity = "manage_daraja"
    scroll_anchor = ""

    def get_object(self, queryset=None):
        obj = DarajaConfig.load()
        if self.request.method == "GET":
            apply_sandbox_to_instance(obj, self.request, force=True)
        return obj

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.object
        context["secrets"] = {field: config.secret_is_set(field) for field in SECRET_FIELDS}
        context["sandbox_defaults"] = sandbox_defaults_payload(self.request)
        context["integration"] = integration_status(config, self.request)
        context["scroll_anchor"] = self.scroll_anchor
        return context

    def form_valid(self, form):
        if self.request.POST.get("intent") == "enable":
            form.instance.b2b_enabled = True
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        write_audit(
            self.request,
            "daraja.setup.saved",
            object_type="daraja",
            object_id=self.object.pk,
            detail={
                "environment": self.object.environment,
                "shortcode": self.object.shortcode,
                "stk_ready": self.object.stk_ready,
                "balance_ready": self.object.balance_ready,
                "b2c_ready": self.object.b2c_ready,
                "b2b_ready": self.object.b2b_ready,
                "agent_shop_ready": self.object.agent_shop_ready,
            },
        )
        status = integration_status(self.object, self.request)
        if status["integrated"]:
            messages.success(self.request, "Daraja setup saved. Successfully integrated.")
        elif self.request.POST.get("intent") == "test":
            messages.error(self.request, status["detail"])
        else:
            messages.success(self.request, "Daraja setup saved. " + status["detail"])
        return response


class DarajaStkSetupView(DarajaSetupView):
    scroll_anchor = "stk"


class DarajaBalanceSetupView(DarajaSetupView):
    scroll_anchor = "balance"


class DarajaB2CSetupView(DarajaSetupView):
    scroll_anchor = "payouts"


class DarajaB2BSetupView(DarajaSetupView):
    scroll_anchor = "payouts"


class DarajaAgentShopSetupView(DarajaSetupView):
    scroll_anchor = "agent"


class DarajaTestView(RoleRequiredMixin, TemplateView):
    template_name = "core/daraja_test.html"
    required_activity = "manage_daraja"

    def get_config(self):
        return DarajaConfig.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_config()
        expire_stale_queues()
        urls = callback_urls(self.request)
        sandbox = str(config.environment) == "SANDBOX"
        integration = capability_status(config, self.request)
        caps = integration["by_id"]
        context.update(
            {
                "config": config,
                "integration": integration,
                "capabilities": caps,
                "stk_blockers": panel_blockers(integration, "stk"),
                "balance_blockers": panel_blockers(integration, "balance"),
                "b2c_blockers": panel_blockers(integration, "b2c"),
                "b2b_blockers": panel_blockers(integration, "b2b"),
                "runnable_tests": sum(
                    [
                        caps["stk"]["ready"],
                        caps["balance"]["ready"],
                        caps["b2c"]["ready"] or caps["b2b"]["ready"],
                    ]
                ),
                "stk_form": kwargs.get("stk_form")
                or StkPromptForm(
                    initial={
                        "phone": SANDBOX_TEST_PHONE if sandbox else "",
                        "amount": SANDBOX_TEST_AMOUNT,
                        "account_ref": config.stk_account_reference,
                    }
                ),
                "balance_form": kwargs.get("balance_form")
                or BalanceQueryForm(initial={"identifier": config.balance_identifier_type or "4"}),
                "send_form": kwargs.get("send_form")
                or SendMoneyForm(
                    initial={
                        "destination_type": "PHONE",
                        "destination": SANDBOX_TEST_PHONE if sandbox else "",
                        "amount": SANDBOX_TEST_AMOUNT,
                        "account_ref": config.stk_account_reference,
                    }
                ),
                "operations": DarajaOperation.objects.all()[:20],
                "sandbox_test_phone": SANDBOX_TEST_PHONE,
                "sandbox_b2b_destination": SANDBOX_B2B_DESTINATION,
                "is_sandbox": sandbox,
                "live_result_url": urls.get("result_url") or config.result_url,
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("poll") == "1":
            expire_stale_queues()
            self._auto_query_stk()
            rows = [
                {
                    "id": row.pk,
                    "kind": row.kind,
                    "kind_label": row.get_kind_display(),
                    "destination": row.destination or "—",
                    "amount": str(row.amount) if row.amount is not None else "",
                    "status": row.status,
                    "status_label": row.get_status_display(),
                    "summary": row.summary or row.result_desc or "Waiting",
                    "when": timezone.localtime(row.created_at).strftime("%H:%M:%S"),
                    "can_refresh": row.kind == DarajaOperation.Kind.STK and bool(row.checkout_request_id),
                    "watch": row.is_fresh_queue(),
                }
                for row in DarajaOperation.objects.all()[:20]
            ]
            return JsonResponse({"operations": rows})
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        intent = request.POST.get("intent")
        if intent == "refresh":
            return self._refresh_stk(request)
        config = self.get_config()
        client = DarajaClient(config)
        urls = callback_urls(request)
        result_url = urls.get("result_url") or ""
        timeout_url = urls.get("timeout_url") or ""
        stk_callback = urls.get("stk_callback_url") or ""
        try:
            if intent == "stk":
                return self._run_stk(request, client, config, stk_callback)
            if intent == "balance":
                return self._run_balance(request, client, result_url, timeout_url)
            if intent == "send":
                return self._run_send(request, client, result_url, timeout_url)
        except DarajaError as exc:
            messages.error(request, str(exc))
            return redirect("core:daraja-test")
        messages.error(request, "Choose an action on this page.")
        return redirect("core:daraja-test")

    def _redact(self, payload: dict) -> dict:
        data = dict(payload or {})
        for key in ("SecurityCredential", "Password"):
            if key in data:
                data[key] = "[redacted]"
        return data

    def _save_operation(self, **kwargs):
        kwargs.setdefault("created_by", self.request.user)
        operation = DarajaOperation.objects.create(**kwargs)
        write_audit(
            self.request,
            f"daraja.{operation.kind.lower()}.queued",
            object_type="daraja_operation",
            object_id=operation.pk,
            detail={"destination": operation.destination, "amount": str(operation.amount or "")},
        )
        return operation

    def _ack_fields(self, body: dict) -> dict:
        return {
            "merchant_request_id": body.get("MerchantRequestID") or "",
            "checkout_request_id": body.get("CheckoutRequestID") or "",
            "conversation_id": body.get("ConversationID") or "",
            "originator_conversation_id": body.get("OriginatorConversationID") or "",
            "result_desc": (body.get("ResponseDescription") or body.get("CustomerMessage") or "")[:255],
            "response_payload": body,
        }

    def _run_stk(self, request, client, config, callback_url):
        form = StkPromptForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(stk_form=form))
        data = form.cleaned_data
        body, payload = client.stk_push(
            phone=data["phone"],
            amount=data["amount"],
            account_ref=data["account_ref"] or config.stk_account_reference,
            callback_url=callback_url,
        )
        operation = self._save_operation(
            kind=DarajaOperation.Kind.STK,
            destination=payload["PhoneNumber"],
            amount=data["amount"],
            account_ref=payload["AccountReference"],
            request_payload=self._redact(payload),
            summary=body.get("CustomerMessage") or "STK prompt sent.",
            **self._ack_fields(body),
        )
        messages.success(
            request,
            body.get("CustomerMessage") or "STK prompt sent. Ask the customer to enter PIN.",
        )
        write_audit(
            request,
            "daraja.stk.sent",
            object_type="daraja_operation",
            object_id=operation.pk,
            detail={"checkout": operation.checkout_request_id},
        )
        return redirect("core:daraja-test")

    def _run_balance(self, request, client, result_url, timeout_url):
        form = BalanceQueryForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(balance_form=form))
        body, payload, party_a = client.account_balance(
            result_url=result_url,
            timeout_url=timeout_url,
            identifier=form.cleaned_data["identifier"],
        )
        operation = self._save_operation(
            kind=DarajaOperation.Kind.BALANCE,
            destination=party_a,
            request_payload=self._redact(payload),
            summary=body.get("ResponseDescription") or "Balance requested. Waiting for Daraja result.",
            **self._ack_fields(body),
        )
        operation = wait_for_result(operation)
        self._flash_result(
            request,
            operation,
            pending="Balance requested. This page updates as soon as Safaricom posts the float.",
        )
        write_audit(request, "daraja.balance.sent", object_type="daraja_operation", object_id=operation.pk)
        return redirect("core:daraja-test")

    def _run_send(self, request, client, result_url, timeout_url):
        form = SendMoneyForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(send_form=form))
        data = form.cleaned_data
        dest_type = data["destination_type"]
        if dest_type == SendMoneyForm.TYPE_PHONE:
            if not client.config.b2c_ready:
                raise DarajaError("Phone payout is not ready. Turn on B2C on Daraja setup.")
            body, payload, dest = client.b2c_send(
                phone=data["destination"],
                amount=data["amount"],
                result_url=result_url,
                timeout_url=timeout_url,
            )
            kind = DarajaOperation.Kind.B2C
        else:
            if not client.config.b2b_ready:
                raise DarajaError("Paybill/till payout is not ready. Turn on B2B on Daraja setup.")
            body, payload, dest = client.b2b_send(
                destination=data["destination"],
                amount=data["amount"],
                to_till=dest_type == SendMoneyForm.TYPE_TILL,
                account_ref=data.get("account_ref") or "",
                result_url=result_url,
                timeout_url=timeout_url,
            )
            kind = DarajaOperation.Kind.B2B
        operation = self._save_operation(
            kind=kind,
            destination=dest,
            amount=data["amount"],
            account_ref=data.get("account_ref") or "",
            request_payload=self._redact(payload),
            summary=body.get("ResponseDescription") or "Payout queued.",
            **self._ack_fields(body),
        )
        operation = wait_for_result(operation)
        self._flash_result(
            request,
            operation,
            pending=body.get("ResponseDescription")
            or "Send request accepted. This page updates as soon as Safaricom posts the result.",
        )
        write_audit(request, "daraja.send.sent", object_type="daraja_operation", object_id=operation.pk)
        return redirect("core:daraja-test")

    def _flash_result(self, request, operation, *, pending: str):
        if operation.status == DarajaOperation.Status.SUCCESS:
            messages.success(request, operation.summary or operation.result_desc or "Completed.")
        elif operation.status == DarajaOperation.Status.FAILED:
            messages.error(request, operation.summary or operation.result_desc or "Daraja returned a failure.")
        elif operation.status == DarajaOperation.Status.TIMEOUT:
            messages.error(request, operation.summary or "Safaricom timed out.")
        else:
            messages.success(request, pending)

    def _refresh_stk(self, request):
        pk = request.POST.get("operation_id")
        operation = DarajaOperation.objects.filter(pk=pk, kind=DarajaOperation.Kind.STK).first()
        if not operation or not operation.checkout_request_id:
            messages.error(request, "That STK prompt cannot be queried yet.")
            return redirect("core:daraja-test")
        try:
            body = DarajaClient(self.get_config()).stk_query(operation.checkout_request_id)
        except DarajaError as exc:
            messages.error(request, str(exc))
            return redirect("core:daraja-test")
        apply_stk_query(operation, body)
        messages.success(request, operation.summary or operation.result_desc or "STK status updated.")
        return redirect("core:daraja-test")

    def _auto_query_stk(self):
        client = None
        queued = DarajaOperation.objects.filter(
            kind=DarajaOperation.Kind.STK,
            status=DarajaOperation.Status.QUEUED,
        ).exclude(checkout_request_id="")
        for operation in queued[:8]:
            try:
                if client is None:
                    client = DarajaClient(self.get_config())
                body = client.stk_query(operation.checkout_request_id)
            except DarajaError:
                continue
            apply_stk_query(operation, body)

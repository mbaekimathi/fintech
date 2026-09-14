from django.conf import settings as django_settings
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, UpdateView

from accounts.mixins import ApprovedRequiredMixin, RoleRequiredMixin
from accounts.models import User
from accounts.utils import write_audit
from integrations.callbacks import apply_stk_query, expire_stale_queues, wait_for_result
from integrations.daraja import (
    SANDBOX_B2B_DESTINATION,
    SANDBOX_TEST_AMOUNT,
    SANDBOX_TEST_PHONE,
    apply_sandbox_to_instance,
    callback_urls,
    integration_status,
    sandbox_defaults_payload,
)
from integrations.daraja_client import DarajaClient, DarajaError
from integrations.forms import (
    SECRET_FIELDS,
    BalanceQueryForm,
    DarajaSetupForm,
    SendMoneyForm,
    StkPromptForm,
)
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import ConnectedSystem, LedgerEntry, PaybillAccount


class DashboardView(ApprovedRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
                "recent_entries": LedgerEntry.objects.select_related(
                    "paybill_account", "connected_system"
                )[:8],
            }
        )
        return context


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


class DarajaSetupView(RoleRequiredMixin, UpdateView):
    template_name = "core/daraja.html"
    form_class = DarajaSetupForm
    success_url = reverse_lazy("core:daraja")
    context_object_name = "config"
    allowed_roles = (
        User.Role.ADMIN,
        User.Role.MANAGER,
        User.Role.IT_SUPPORT,
    )

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
        return context

    def form_valid(self, form):
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


DARAJA_ROLES = (
    User.Role.ADMIN,
    User.Role.MANAGER,
    User.Role.IT_SUPPORT,
)


class DarajaTestView(RoleRequiredMixin, TemplateView):
    template_name = "core/daraja_test.html"
    allowed_roles = DARAJA_ROLES

    def get_config(self):
        return DarajaConfig.load()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_config()
        expire_stale_queues()
        urls = callback_urls(self.request)
        sandbox = str(config.environment) == "SANDBOX"
        context.update(
            {
                "config": config,
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
        if dest_type == "PHONE":
            body, payload, dest = client.b2c_send(
                phone=data["destination"],
                amount=data["amount"],
                result_url=result_url,
                timeout_url=timeout_url,
            )
            kind = DarajaOperation.Kind.B2C
        else:
            body, payload, dest = client.b2b_send(
                destination=data["destination"],
                amount=data["amount"],
                to_till=dest_type == "TILL",
                account_ref=data["account_ref"],
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

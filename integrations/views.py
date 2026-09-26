from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.authentication import MonitorPrincipal, SystemPrincipal
from integrations.serializers import CollectionStkSerializer
from paybill.collection_stk import initiate_monitor_stk_collection
from integrations.daraja_client import DarajaError
import json
import uuid

from integrations.c2b import normalize_c2b_payload, post_c2b_ledger, validate_c2b_payment
from integrations.callbacks import apply_result_callback, apply_stk_callback, apply_timeout_callback
from integrations.serializers import LedgerEntrySerializer
from paybill.models import LedgerEntry, PaybillAccount


class IsConnectedSystem(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, SystemPrincipal)


class IsCollectionMonitor(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, MonitorPrincipal)


class CollectionStkCollectView(APIView):
    """STK collect using the monitor's collection code and Daraja credentials."""

    permission_classes = [IsCollectionMonitor]

    def post(self, request):
        principal: MonitorPrincipal = request.user
        serializer = CollectionStkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            operation = initiate_monitor_stk_collection(
                monitor=principal.monitor,
                phone=serializer.validated_data["phone"],
                amount=serializer.validated_data["amount"],
                request=request,
            )
        except DarajaError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "collection_code": principal.monitor.collection_code,
                "operation_id": operation.pk,
                "checkout_request_id": operation.checkout_request_id,
                "summary": operation.summary,
                "status": operation.status,
            },
            status=status.HTTP_201_CREATED,
        )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "nexus-ledger"})


class LedgerIngestView(generics.CreateAPIView):
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsConnectedSystem]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["system"] = self.request.user.system
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LedgerListView(generics.ListAPIView):
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsConnectedSystem]

    def get_queryset(self):
        return LedgerEntry.objects.filter(connected_system=self.request.user.system)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["system"] = self.request.user.system
        return context


class PaybillCatalogView(APIView):
    permission_classes = [IsConnectedSystem]

    def get(self, request):
        rows = PaybillAccount.objects.filter(connected_system=request.user.system, is_active=True)
        return Response(
            [
                {
                    "paybill_number": row.paybill_number,
                    "account_name": row.account_name,
                    "provider": row.provider,
                }
                for row in rows
            ]
        )


def _json_request_payload(request) -> dict:
    data = request.data if isinstance(getattr(request, "data", None), dict) else {}
    if data:
        return data
    if hasattr(request, "POST") and request.POST:
        return dict(request.POST)
    raw = getattr(request, "body", b"") or b""
    if raw:
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _c2b_request_payload(request) -> dict:
    return normalize_c2b_payload(_json_request_payload(request))


@method_decorator(csrf_exempt, name="dispatch")
class DarajaC2BValidationView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response(validate_c2b_payment(_c2b_request_payload(request)))


@method_decorator(csrf_exempt, name="dispatch")
class DarajaC2BConfirmationView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        post_c2b_ledger(_c2b_request_payload(request))
        return Response({"ResultCode": 0, "ResultDesc": "Success", "ThirdPartyTransID": str(uuid.uuid4())[:20]})


@method_decorator(csrf_exempt, name="dispatch")
class DarajaStkCallbackView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        apply_stk_callback(_json_request_payload(request))
        return Response({"ResultCode": 0, "ResultDesc": "Success"})


@method_decorator(csrf_exempt, name="dispatch")
class DarajaResultView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        apply_result_callback(request.data if isinstance(request.data, dict) else {})
        return Response({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class DarajaTimeoutView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        apply_timeout_callback(request.data if isinstance(request.data, dict) else {})
        return Response({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class DarajaAgentCallbackView(APIView):
    """Placeholder endpoints for future official Safaricom agent deposit/withdraw callbacks."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({"ResultCode": 0, "ResultDesc": "Accepted", "status": "ok"})

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.authentication import SystemPrincipal
from integrations.callbacks import apply_result_callback, apply_stk_callback, apply_timeout_callback
from integrations.serializers import LedgerEntrySerializer
from paybill.models import LedgerEntry, PaybillAccount


class IsConnectedSystem(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, SystemPrincipal)


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


@method_decorator(csrf_exempt, name="dispatch")
class DarajaStkCallbackView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        apply_stk_callback(request.data if isinstance(request.data, dict) else {})
        return Response({"status": "ok"})


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

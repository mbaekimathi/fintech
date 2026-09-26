from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from integrations.models import APICredential, hash_api_key
from paybill.models import CollectionMonitor, CollectionMonitorCredential, ConnectedSystem, hash_collection_api_key


class SystemPrincipal:
    """Authenticated connected system presented to DRF as request.user."""

    def __init__(self, system: ConnectedSystem, credential: APICredential):
        self.system = system
        self.credential = credential
        self.is_authenticated = True
        self.is_anonymous = False
        self.pk = system.pk

    def __str__(self):
        return self.system.slug


class MonitorPrincipal:
    """Authenticated collection monitor for STK collect API calls."""

    def __init__(self, monitor: CollectionMonitor, credential: CollectionMonitorCredential):
        self.monitor = monitor
        self.credential = credential
        self.is_authenticated = True
        self.is_anonymous = False
        self.pk = monitor.pk

    def __str__(self):
        return self.monitor.collection_code


class APIKeyAuthentication(BaseAuthentication):
    keyword = "X-API-Key"

    def authenticate(self, request):
        raw = request.headers.get(self.keyword) or request.META.get("HTTP_X_API_KEY")
        if not raw:
            return None
        if raw.startswith("cm_"):
            digest = hash_collection_api_key(raw)
            try:
                cred = CollectionMonitorCredential.objects.select_related("monitor").get(
                    key_hash=digest,
                    is_active=True,
                )
            except CollectionMonitorCredential.DoesNotExist:
                raise AuthenticationFailed("Invalid collection API key.")
            monitor = cred.monitor
            if not monitor.is_active:
                raise AuthenticationFailed("This collection account is disabled.")
            cred.mark_used()
            return (MonitorPrincipal(monitor, cred), cred)
        digest = hash_api_key(raw)
        try:
            cred = APICredential.objects.select_related("system").get(key_hash=digest, is_active=True)
        except APICredential.DoesNotExist:
            raise AuthenticationFailed("Invalid API key.")
        if not cred.system.is_active:
            raise AuthenticationFailed("This connected system is disabled.")
        cred.mark_used()
        return (SystemPrincipal(cred.system, cred), cred)

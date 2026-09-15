"""Web Push (phone notification tray) helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from django.conf import settings

logger = logging.getLogger(__name__)


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _ensure_vapid_keys() -> tuple[str, str]:
    public = (getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "") or "").strip()
    private = (getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "") or "").strip()
    if public and private:
        return public, private

    path = Path(settings.BASE_DIR) / ".vapid.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            public = (data.get("public_key") or "").strip()
            private = (data.get("private_key") or "").strip()
            if public and private:
                return public, private
        except (OSError, json.JSONDecodeError, TypeError):
            logger.exception("Could not read %s", path)

    if not getattr(settings, "DEBUG", False):
        return "", ""

    from py_vapid import Vapid

    vapid = Vapid()
    vapid.generate_keys()
    public_bytes = vapid.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public = _b64url(public_bytes)
    private = vapid.private_pem().decode("ascii")
    try:
        path.write_text(
            json.dumps({"public_key": public, "private_key": private}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Could not write %s", path)
    return public, private


def webpush_enabled() -> bool:
    public, private = _ensure_vapid_keys()
    return bool(public and private)


def vapid_public_key() -> str:
    public, _private = _ensure_vapid_keys()
    return public


def vapid_private_key() -> str:
    _public, private = _ensure_vapid_keys()
    return private


def vapid_claims() -> dict:
    contact = (getattr(settings, "WEBPUSH_VAPID_CONTACT", "") or "mailto:admin@localhost").strip()
    if not contact.startswith("mailto:"):
        contact = f"mailto:{contact}"
    return {"sub": contact}


def send_web_push_to_user(user, *, title: str, body: str = "", url: str = "/") -> int:
    """Send a tray notification to every saved browser subscription for this user."""
    if not user or not getattr(user, "pk", None) or not webpush_enabled():
        return 0

    from pywebpush import WebPushException, webpush

    from core.models import PushSubscription

    payload = json.dumps(
        {
            "title": title[:120],
            "body": (body or "")[:180],
            "url": url or "/",
        }
    )
    private = vapid_private_key()
    claims = vapid_claims()
    sent = 0
    stale_ids: list[int] = []
    for row in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info=row.as_subscription_info(),
                data=payload,
                vapid_private_key=private,
                vapid_claims=claims,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {404, 410}:
                stale_ids.append(row.pk)
            else:
                logger.warning("Web push failed for user %s: %s", user.pk, exc)
        except Exception:
            logger.exception("Web push error for user %s", user.pk)
    if stale_ids:
        PushSubscription.objects.filter(pk__in=stale_ids).delete()
    return sent

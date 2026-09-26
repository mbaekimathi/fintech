"""Checks that collected static files match the shipped frontend (approval flow)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.conf import settings

APPROVAL_JS_MARKERS: tuple[str, ...] = (
    "initReviewApproval",
    "triggerApprovalFromForm",
    "pendingPollBootstrapped",
    "installGlobalApprovalClickHandler",
)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def app_js_paths() -> tuple[Path, Path]:
    base = Path(settings.BASE_DIR)
    return base / "static" / "js" / "app.js", base / "staticfiles" / "js" / "app.js"


def app_js_fingerprint(data: bytes) -> str:
    if not data:
        return ""
    return hashlib.sha256(data).hexdigest()[:12]


def deploy_static_report() -> dict:
    source_path, collected_path = app_js_paths()
    source_bytes = _read(source_path)
    collected_bytes = _read(collected_path)
    source_text = source_bytes.decode("utf-8", errors="replace")
    collected_text = collected_bytes.decode("utf-8", errors="replace")

    markers = {
        name: name in collected_text
        for name in APPROVAL_JS_MARKERS
    }
    collected_ok = bool(collected_bytes) and all(markers.values())
    source_collected_match = (
        bool(source_bytes)
        and bool(collected_bytes)
        and app_js_fingerprint(source_bytes) == app_js_fingerprint(collected_bytes)
    )

    return {
        "asset_version": getattr(settings, "ASSET_VERSION", ""),
        "source_app_js_bytes": len(source_bytes),
        "collected_app_js_bytes": len(collected_bytes),
        "source_fingerprint": app_js_fingerprint(source_bytes),
        "collected_fingerprint": app_js_fingerprint(collected_bytes),
        "source_collected_match": source_collected_match,
        "approval_js_markers": markers,
        "collected_ok": collected_ok,
        "ok": collected_ok and source_collected_match,
    }

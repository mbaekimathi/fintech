"""Checks that collected static files match the shipped frontend (approval flow)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from django.conf import settings

APPROVAL_JS_MARKERS: tuple[str, ...] = (
    "pendingPollBootstrapped",
    "beginApprovalFlow",
    "installGlobalApprovalClickHandler",
    "data-stk-approval-use-app",
)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def static_js_paths(name: str) -> tuple[Path, Path]:
    base = Path(settings.BASE_DIR)
    return base / "static" / "js" / name, base / "staticfiles" / "js" / name


def app_js_paths() -> tuple[Path, Path]:
    return static_js_paths("app.js")


def payment_approval_js_paths() -> tuple[Path, Path]:
    return static_js_paths("payment-approval.js")


def file_fingerprint(data: bytes) -> str:
    if not data:
        return ""
    return hashlib.sha256(data).hexdigest()[:12]


def app_js_fingerprint(data: bytes) -> str:
    return file_fingerprint(data)


def _match_report(source_path: Path, collected_path: Path, markers: tuple[str, ...]) -> dict:
    source_bytes = _read(source_path)
    collected_bytes = _read(collected_path)
    collected_text = collected_bytes.decode("utf-8", errors="replace")
    marker_map = {name: name in collected_text for name in markers}
    collected_ok = bool(collected_bytes) and all(marker_map.values())
    source_collected_match = (
        bool(source_bytes)
        and bool(collected_bytes)
        and file_fingerprint(source_bytes) == file_fingerprint(collected_bytes)
    )
    return {
        "source_bytes": len(source_bytes),
        "collected_bytes": len(collected_bytes),
        "source_fingerprint": file_fingerprint(source_bytes),
        "collected_fingerprint": file_fingerprint(collected_bytes),
        "source_collected_match": source_collected_match,
        "approval_js_markers": marker_map,
        "collected_ok": collected_ok,
        "ok": collected_ok and source_collected_match,
    }


def deploy_static_report() -> dict:
    app_source, app_collected = app_js_paths()
    pa_source, pa_collected = payment_approval_js_paths()

    app_report = _match_report(app_source, app_collected, ())
    pa_report = _match_report(pa_source, pa_collected, APPROVAL_JS_MARKERS)

    return {
        "asset_version": getattr(settings, "ASSET_VERSION", ""),
        "source_app_js_bytes": app_report["source_bytes"],
        "collected_app_js_bytes": app_report["collected_bytes"],
        "source_fingerprint": app_report["source_fingerprint"],
        "collected_fingerprint": app_report["collected_fingerprint"],
        "source_collected_match": app_report["source_collected_match"],
        "approval_js_markers": pa_report["approval_js_markers"],
        "source_payment_approval_js_bytes": pa_report["source_bytes"],
        "collected_payment_approval_js_bytes": pa_report["collected_bytes"],
        "payment_approval_fingerprint": pa_report["source_fingerprint"],
        "collected_payment_approval_fingerprint": pa_report["collected_fingerprint"],
        "payment_approval_collected_match": pa_report["source_collected_match"],
        "collected_ok": pa_report["collected_ok"],
        "ok": app_report["source_collected_match"] and pa_report["ok"],
    }

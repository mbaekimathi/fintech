#!/usr/bin/env python
"""Probe hosted deploy health and static approval assets (no Django required)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://fin.richcom.co.ke"


def fetch(url: str, timeout: float = 20.0) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "NEXUS-deploy-check/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")
    health_url = f"{base}/health/deploy/"
    static_url = f"{base}/static/js/payment-approval.js"

    print(f"Base URL: {base}\n")

    status, body = fetch(health_url)
    print(f"GET {health_url} -> HTTP {status}")
    try:
        report = json.loads(body)
    except json.JSONDecodeError:
        print("Non-JSON health response (first 400 chars):")
        print(body[:400])
        return 1

    print(json.dumps(report, indent=2))

    static_status, static_body = fetch(static_url)
    print(f"\nGET {static_url} -> HTTP {static_status}")
    if static_status == 200:
        print(f"  payment-approval.js length: {len(static_body)} bytes")
        for marker in (
            "buildStkPollUrl",
            "data-stk-approval-use-app",
            "stkLipaCharge",
        ):
            print(f"  marker {marker!r}: {'yes' if marker in static_body else 'NO'}")
    else:
        print("  payment-approval.js is NOT served — approval STK/poll UI will be broken.")

    ok = bool(report.get("ok")) and static_status == 200
    if ok:
        print("\nDeploy static check: OK")
        return 0

    print("\nDeploy static check: FAILED")
    print("On the server (cPanel app dir, e.g. ~/FIN) run:")
    print("  bash deploy.sh")
    print("Or manually:")
    print("  git pull origin main")
    print("  grep -q '^APPROVAL_STK_LIPA_CHARGE=' .env || echo 'APPROVAL_STK_LIPA_CHARGE=0' >> .env")
    print("  python manage.py migrate --noinput")
    print("  python manage.py collectstatic --noinput --clear")
    print("  python manage.py verify_static")
    print("  mkdir -p tmp && touch tmp/restart.txt")
    print(f"Then re-run: python scripts/check_production_deploy.py {base}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

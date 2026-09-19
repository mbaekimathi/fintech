#!/usr/bin/env python
"""Run approval-flow tests in a loop until they pass (or max attempts)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = [
    "core.tests.AppSettingsTests",
    "core.tests.NotificationFlowTests",
    "paybill.tests.PendingTransactionsTests",
    "paybill.tests.MoneyRequestReviewTests",
]


def run_once() -> int:
    cmd = [
        sys.executable,
        "manage.py",
        "test",
        *LABELS,
        "--keepdb",
        "-v",
        "1",
    ]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def main() -> int:
    max_attempts = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for attempt in range(1, max_attempts + 1):
        print(f"\n=== Approval test loop attempt {attempt}/{max_attempts} ===\n")
        code = run_once()
        if code == 0:
            print("\nAll approval tests passed.")
            return 0
        print(f"\nAttempt {attempt} failed with exit code {code}.")
    print("\nApproval tests still failing after all attempts.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

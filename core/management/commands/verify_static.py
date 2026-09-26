"""Fail deploy if staticfiles/js/app.js is stale (common cPanel issue)."""

from django.core.management.base import BaseCommand, CommandError

from core.static_health import deploy_static_report


class Command(BaseCommand):
    help = "Verify collectstatic copied payment-approval.js (and app.js) for deploy."

    def handle(self, *args, **options):
        report = deploy_static_report()
        self.stdout.write(f"ASSET_VERSION={report['asset_version']}")
        self.stdout.write(
            f"source={report['source_app_js_bytes']}b "
            f"collected={report['collected_app_js_bytes']}b "
            f"match={report['source_collected_match']}"
        )
        for name, present in report["approval_js_markers"].items():
            self.stdout.write(f"  {name}: {'ok' if present else 'MISSING'}")

        self.stdout.write(
            f"payment-approval source={report['source_payment_approval_js_bytes']}b "
            f"collected={report['collected_payment_approval_js_bytes']}b "
            f"match={report['payment_approval_collected_match']}"
        )

        if not report["ok"]:
            raise CommandError(
                "staticfiles/js/payment-approval.js is missing or stale. "
                "Run: python manage.py collectstatic --noinput --clear "
                "then restart the app (touch tmp/restart.txt)."
            )
        self.stdout.write(self.style.SUCCESS("Static files OK for payment approval."))

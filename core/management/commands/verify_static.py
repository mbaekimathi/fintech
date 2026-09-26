"""Fail deploy if staticfiles/js/app.js is stale (common cPanel issue)."""

from django.core.management.base import BaseCommand, CommandError

from core.static_health import deploy_static_report


class Command(BaseCommand):
    help = "Verify collectstatic copied app.js including payment approval frontend."

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

        if not report["ok"]:
            raise CommandError(
                "staticfiles/js/app.js is missing approval code. "
                "Run: python manage.py collectstatic --noinput "
                "then restart the app (touch tmp/restart.txt)."
            )
        self.stdout.write(self.style.SUCCESS("Static files OK for payment approval."))

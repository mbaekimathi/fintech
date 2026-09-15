"""Expire Daraja operations that never received a ResultURL callback."""

from django.core.management.base import BaseCommand

from integrations.callbacks import expire_stale_queues


class Command(BaseCommand):
    help = (
        "Mark queued Daraja payouts as timed out when Safaricom never posts a result. "
        "Linked money requests return to Pending so staff can retry."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--seconds",
            type=int,
            default=900,
            help="Age in seconds before a queued operation is treated as timed out (default: 900).",
        )

    def handle(self, *args, **options):
        seconds = max(60, int(options["seconds"]))
        count = expire_stale_queues(seconds=seconds)
        self.stdout.write(self.style.SUCCESS(f"Expired {count} queued Daraja operation(s)."))

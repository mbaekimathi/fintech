from django.core.management.base import BaseCommand, CommandError

from integrations.models import APICredential
from paybill.models import ConnectedSystem


class Command(BaseCommand):
    help = "Issue a new API key for a connected system (shown once)."

    def add_arguments(self, parser):
        parser.add_argument("--system", required=True, help="Connected system slug")
        parser.add_argument("--name", default="primary")

    def handle(self, *args, **options):
        try:
            system = ConnectedSystem.objects.get(slug=options["system"])
        except ConnectedSystem.DoesNotExist as exc:
            raise CommandError(f"Unknown system slug: {options['system']}") from exc
        cred, raw = APICredential.issue(system, name=options["name"])
        self.stdout.write(self.style.WARNING("Store this API key now. It is not shown again."))
        self.stdout.write(raw)
        self.stdout.write(f"Prefix: {cred.key_prefix}")

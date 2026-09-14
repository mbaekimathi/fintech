from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User
from integrations.models import APICredential
from paybill.models import ConnectedSystem, LedgerEntry, PaybillAccount


class Command(BaseCommand):
    help = "Create the first admin, a sample connected system, and an API key."

    def add_arguments(self, parser):
        parser.add_argument("--code", default="100001", help="Admin 6-digit staff code")
        parser.add_argument("--password", default="135790", help="Admin 6-digit password")
        parser.add_argument("--email", default="admin@nexus.local")
        parser.add_argument("--name", default="Hub Admin")

    @transaction.atomic
    def handle(self, *args, **options):
        code = str(options["code"]).zfill(6)
        password = str(options["password"])
        if not code.isdigit() or len(code) != 6:
            raise CommandError("Admin staff code must be 6 digits.")
        if not password.isdigit() or len(password) != 6:
            raise CommandError("Admin password must be 6 digits.")

        first, _, last = options["name"].partition(" ")
        admin, created = User.objects.get_or_create(
            staff_code=code,
            defaults={
                "email": options["email"],
                "first_name": first or "Hub",
                "last_name": last or "Admin",
                "role": User.Role.ADMIN,
                "is_approved": True,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        if created:
            admin.set_password(password)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"Admin created: {admin.staff_code}"))
        else:
            self.stdout.write(f"Admin already exists: {admin.staff_code}")

        system, _ = ConnectedSystem.objects.get_or_create(
            slug="flagship-pos",
            defaults={
                "name": "Flagship POS",
                "description": "Sample sister system that posts collections into NEXUS.",
                "created_by": admin,
            },
        )
        account, _ = PaybillAccount.objects.get_or_create(
            paybill_number="888555",
            connected_system=system,
            defaults={
                "account_name": "Flagship store collections",
                "provider": PaybillAccount.Provider.MPESA,
            },
        )
        if not LedgerEntry.objects.filter(reference="NX-DEMO-001").exists():
            LedgerEntry.objects.create(
                reference="NX-DEMO-001",
                paybill_account=account,
                connected_system=system,
                amount=Decimal("1500.00"),
                payer_name="Amina Otieno",
                payer_phone="254700000001",
                account_ref="INV-1042",
                narrative="Seed posting",
            )

        if not system.credentials.exists():
            cred, raw = APICredential.issue(system, name="bootstrap")
            self.stdout.write(self.style.WARNING("Store this API key now. It is not shown again."))
            self.stdout.write(raw)
            self.stdout.write(f"Prefix: {cred.key_prefix}")
        else:
            self.stdout.write("API key already issued for Flagship POS.")

        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))

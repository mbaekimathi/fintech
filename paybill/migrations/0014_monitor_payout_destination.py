from django.db import migrations, models


def copy_phone_to_destination(apps, schema_editor):
    CollectionMonitor = apps.get_model("paybill", "CollectionMonitor")
    for row in CollectionMonitor.objects.exclude(auto_payout_phone=""):
        if not (row.auto_payout_destination or "").strip():
            row.auto_payout_destination = row.auto_payout_phone
            row.save(update_fields=["auto_payout_destination"])


class Migration(migrations.Migration):

    dependencies = [
        ("paybill", "0013_collection_monitor_auto_payout"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionmonitor",
            name="auto_payout_destination_type",
            field=models.CharField(
                choices=[("PAYBILL", "Paybill"), ("TILL", "Till (Buy Goods)"), ("PHONE", "Phone number")],
                default="PHONE",
                help_text="Where automated payouts go after collection.",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="collectionmonitor",
            name="auto_payout_destination",
            field=models.CharField(
                blank=True,
                help_text="Phone, paybill, or till number for automated payout.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="collectionmonitor",
            name="auto_payout_account_ref",
            field=models.CharField(
                blank=True,
                help_text="Paybill account number when destination type is paybill.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="collectionmonitor",
            name="auto_payout_utility_first",
            field=models.BooleanField(
                default=False,
                help_text="Move collected amount from utility to working float before B2B/B2C payout.",
            ),
        ),
        migrations.RunPython(copy_phone_to_destination, migrations.RunPython.noop),
    ]

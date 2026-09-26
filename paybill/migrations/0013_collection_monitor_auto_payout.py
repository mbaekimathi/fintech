from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("paybill", "0012_monitor_collection_credentials"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionmonitor",
            name="auto_payout_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When on, each completed inbound collection is sent to the client phone via B2C.",
            ),
        ),
        migrations.AddField(
            model_name="collectionmonitor",
            name="auto_payout_phone",
            field=models.CharField(
                blank=True,
                help_text="Client M-Pesa number (07… or 254…) to receive automated transfers.",
                max_length=20,
            ),
        ),
    ]

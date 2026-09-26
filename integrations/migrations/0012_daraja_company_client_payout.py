from django.db import migrations, models

import accounts.fields


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0011_monitor_collection_credentials"),
    ]

    operations = [
        migrations.AddField(
            model_name="darajaconfig",
            name="company_client_auto_payout",
            field=accounts.fields.MysqlBooleanEnumField(
                default=False,
                help_text="When on, inbound collections for this registered company auto-send to the company client phone (unless a collection account overrides).",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="company_client_payout_phone",
            field=models.CharField(
                blank=True,
                help_text="Default client M-Pesa number for the registered hub company (07… or 254…).",
                max_length=20,
            ),
        ),
    ]

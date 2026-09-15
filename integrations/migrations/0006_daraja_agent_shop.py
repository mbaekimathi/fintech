import accounts.fields
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0005_daraja_org_shortcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_cash_in_account_ref",
            field=models.CharField(
                blank=True,
                help_text="Default STK account reference for cash-in (e.g. AGENT or till code).",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_cash_in_enabled",
            field=accounts.fields.MysqlBooleanEnumField(
                default=True,
                help_text="Cash-in: customer pays into the hub (STK) — deposit against a phone number.",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_cash_in_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Fixed fee (KES) charged on cash-in. 0 means no fee.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_cash_out_enabled",
            field=accounts.fields.MysqlBooleanEnumField(
                default=True,
                help_text="Cash-out: hub pays a phone (B2C) — withdraw to a phone number.",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_cash_out_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Fixed fee (KES) charged on cash-out. 0 means no fee.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_daily_limit",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Max KES per agent per day. Use 0 for no extra daily cap.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_float_warn_kes",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("1000"),
                help_text="Warn on the test page when live float falls below this amount.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_max_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("70000"),
                help_text="Maximum KES per cash-in or cash-out.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_min_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("10"),
                help_text="Minimum KES per cash-in or cash-out.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_receipt_prefix",
            field=models.CharField(
                blank=True,
                default="AG",
                help_text="Prefix for agent receipt / reference numbers.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_shop_enabled",
            field=accounts.fields.MysqlBooleanEnumField(
                default=False,
                help_text="Turn on agent-shop deposit and withdraw by phone on this shortcode.",
            ),
        ),
    ]

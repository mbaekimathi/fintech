import accounts.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0006_daraja_agent_shop"),
    ]

    operations = [
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_api_base_url",
            field=models.URLField(
                blank=True,
                help_text="API host Safaricom gives you (leave blank to use the shared Daraja host).",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_api_enabled",
            field=accounts.fields.MysqlBooleanEnumField(
                default=False,
                help_text="Use official agent deposit/withdraw APIs when Safaricom has issued them.",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_api_notes",
            field=models.TextField(
                blank=True,
                help_text="Paste product names, sandbox notes, or support ticket refs from Safaricom.",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_channel",
            field=accounts.fields.MysqlChoiceEnumField(
                choices=[
                    ("BUSINESS", "Business shop (STK collect + B2C payout)"),
                    ("SAFARICOM", "Official Safaricom agent (API when issued)"),
                ],
                default="BUSINESS",
                help_text="Business uses STK/B2C on your paybill. Safaricom agent uses official agent APIs after registration.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_consumer_key",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_consumer_secret",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_deposit_callback_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_deposit_command",
            field=models.CharField(
                blank=True,
                help_text="CommandID or product code for agent deposit, when provided.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_deposit_path",
            field=models.CharField(
                blank=True,
                help_text="Relative deposit/cash-in path from the Safaricom API pack, e.g. /mpesa/agent/v1/deposit.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_head_office",
            field=models.CharField(
                blank=True,
                help_text="Agent head-office shortcode, if different from the till.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_initiator_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_operator_id",
            field=models.CharField(
                blank=True,
                help_text="Operator / attendant id if Safaricom issues one for API calls.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_result_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_security_credential",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_store_number",
            field=models.CharField(
                blank=True,
                help_text="Store or outlet reference from your dealer / head office.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_timeout_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_till_number",
            field=models.CharField(
                blank=True,
                help_text="M-Pesa agent till / outlet number from Safaricom.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_track_commission",
            field=accounts.fields.MysqlBooleanEnumField(
                default=True,
                help_text="Record Safaricom agent commission when callbacks or statements expose it.",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_use_shared_app",
            field=accounts.fields.MysqlBooleanEnumField(
                default=True,
                help_text="Reuse the shared Daraja consumer key/secret. Turn off to paste a separate agent app.",
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_withdraw_callback_url",
            field=models.URLField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_withdraw_command",
            field=models.CharField(
                blank=True,
                help_text="CommandID or product code for agent withdraw, when provided.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="darajaconfig",
            name="agent_withdraw_path",
            field=models.CharField(
                blank=True,
                help_text="Relative withdraw/cash-out path from the Safaricom API pack.",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="darajaconfig",
            name="agent_cash_in_account_ref",
            field=models.CharField(
                blank=True,
                help_text="Default account reference for cash-in (e.g. AGENT or till code).",
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="darajaconfig",
            name="agent_cash_in_enabled",
            field=accounts.fields.MysqlBooleanEnumField(
                default=True,
                help_text="Cash-in / deposit for a customer phone.",
            ),
        ),
        migrations.AlterField(
            model_name="darajaconfig",
            name="agent_cash_in_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Your own fee on business-shop cash-in (KES). Not Safaricom commission. 0 = none.",
                max_digits=14,
            ),
        ),
        migrations.AlterField(
            model_name="darajaconfig",
            name="agent_cash_out_enabled",
            field=accounts.fields.MysqlBooleanEnumField(
                default=True,
                help_text="Cash-out / withdraw for a customer phone.",
            ),
        ),
        migrations.AlterField(
            model_name="darajaconfig",
            name="agent_cash_out_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Your own fee on business-shop cash-out (KES). Not Safaricom commission. 0 = none.",
                max_digits=14,
            ),
        ),
        migrations.AlterField(
            model_name="darajaconfig",
            name="agent_float_warn_kes",
            field=models.DecimalField(
                decimal_places=2,
                default=1000,
                help_text="Warn when live float falls below this amount.",
                max_digits=14,
            ),
        ),
    ]

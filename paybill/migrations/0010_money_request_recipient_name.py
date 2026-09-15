from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("paybill", "0009_money_request_failed_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="moneyrequest",
            name="recipient_name",
            field=models.CharField(
                blank=True,
                help_text="Verified recipient or business name from live lookup.",
                max_length=160,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_app_settings"),
    ]

    operations = [
        migrations.RenameField(
            model_name="appsettings",
            old_name="pin_approval_required",
            new_name="app_approval_required",
        ),
        migrations.AlterField(
            model_name="appsettings",
            name="app_approval_required",
            field=models.BooleanField(
                default=False,
                help_text="When on, approvers must enter their 6-digit login password in the app before a payment is sent.",
            ),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="stk_pin_approval_required",
            field=models.BooleanField(
                default=False,
                help_text="When on, approvers must complete an M-Pesa STK PIN prompt on their phone before a payment is sent.",
            ),
        ),
    ]

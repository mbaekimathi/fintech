from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_push_subscription_hash"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "pin_approval_required",
                    models.BooleanField(
                        default=False,
                        help_text="When on, approvers must enter their 6-digit password before a payment is sent.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "App settings",
                "verbose_name_plural": "App settings",
            },
        ),
    ]

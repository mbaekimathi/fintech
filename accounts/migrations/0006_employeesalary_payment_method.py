from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_employeesalary_kenya_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeesalary",
            name="payment_method",
            field=models.CharField(
                choices=[("BANK", "Bank transfer"), ("MPESA", "M-Pesa"), ("CASH", "Cash")],
                default="BANK",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="mpesa_number",
            field=models.CharField(blank=True, max_length=15, verbose_name="M-Pesa number"),
        ),
    ]

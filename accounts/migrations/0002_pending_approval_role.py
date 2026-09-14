from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("PENDING_APPROVAL", "Pending approval"),
                    ("ADMIN", "Admin"),
                    ("MANAGER", "Manager"),
                    ("EMPLOYEE", "Employee"),
                    ("CLIENT", "Client"),
                    ("ACCOUNTS", "Accounts"),
                    ("IT_SUPPORT", "IT Support"),
                ],
                default="PENDING_APPROVAL",
                max_length=20,
            ),
        ),
    ]

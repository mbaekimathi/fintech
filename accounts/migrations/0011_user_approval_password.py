from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_employee_permissions_stk_pin_approval_prompt"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="approval_password",
            field=models.CharField(
                blank=True,
                help_text="Hashed 6-digit password used only to approve payment transfers.",
                max_length=128,
            ),
        ),
    ]

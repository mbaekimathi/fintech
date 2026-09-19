import accounts.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_employee_permissions_app_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeepermissions",
            name="pin_approval_prompt",
            field=accounts.fields.MysqlBooleanEnumField(default=False),
        ),
    ]

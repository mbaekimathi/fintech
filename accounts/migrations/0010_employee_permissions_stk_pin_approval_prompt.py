from django.db import migrations

import accounts.fields


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_employee_permissions_pin_approval_prompt"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeepermissions",
            name="stk_pin_approval_prompt",
            field=accounts.fields.MysqlBooleanEnumField(default=False),
        ),
    ]

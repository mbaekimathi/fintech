import accounts.fields
from django.db import migrations


def _backfill_app_settings(apps, schema_editor):
    EmployeePermissions = apps.get_model("accounts", "EmployeePermissions")
    User = apps.get_model("accounts", "User")
    role_defaults = {
        "ADMIN": True,
        "MANAGER": True,
        "IT_SUPPORT": True,
    }
    for perms in EmployeePermissions.objects.select_related("user").iterator():
        role = getattr(perms.user, "role", "")
        if role_defaults.get(role):
            perms.manage_app_settings = True
            perms.save(update_fields=["manage_app_settings"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_employee_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeepermissions",
            name="manage_app_settings",
            field=accounts.fields.MysqlBooleanEnumField(default=False),
        ),
        migrations.RunPython(_backfill_app_settings, migrations.RunPython.noop),
    ]

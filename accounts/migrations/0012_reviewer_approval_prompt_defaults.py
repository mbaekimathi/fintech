from django.db import migrations


def enable_reviewer_approval_prompts(apps, schema_editor):
    EmployeePermissions = apps.get_model("accounts", "EmployeePermissions")
    EmployeePermissions.objects.filter(review_requests=True).update(
        pin_approval_prompt=True,
        stk_pin_approval_prompt=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_user_approval_password"),
    ]

    operations = [
        migrations.RunPython(enable_reviewer_approval_prompts, migrations.RunPython.noop),
    ]

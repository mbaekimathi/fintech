from django.db import migrations

import accounts.fields


ROLE_ENUM_SQL = """
ENUM(
    'PENDING_APPROVAL',
    'ADMIN',
    'MANAGER',
    'EMPLOYEE',
    'CLIENT',
    'ACCOUNTS',
    'IT_SUPPORT'
)
"""

ROLE_CHOICES = [
    ("PENDING_APPROVAL", "Pending approval"),
    ("ADMIN", "Admin"),
    ("MANAGER", "Manager"),
    ("EMPLOYEE", "Employee"),
    ("CLIENT", "Client"),
    ("ACCOUNTS", "Accounts"),
    ("IT_SUPPORT", "IT Support"),
]


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"ALTER TABLE accounts_user MODIFY COLUMN role {ROLE_ENUM_SQL} NOT NULL DEFAULT 'PENDING_APPROVAL'"
        )
        # tinyint 1 would map to ENUM index 1 if converted directly — go through varchar first
        cursor.execute(
            "ALTER TABLE accounts_user MODIFY COLUMN is_approved VARCHAR(1) NOT NULL DEFAULT '0'"
        )
        cursor.execute(
            "ALTER TABLE accounts_user MODIFY COLUMN is_approved ENUM('0','1') NOT NULL DEFAULT '0'"
        )


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE accounts_user MODIFY COLUMN role VARCHAR(20) NOT NULL DEFAULT 'PENDING_APPROVAL'"
        )
        cursor.execute(
            "ALTER TABLE accounts_user MODIFY COLUMN is_approved TINYINT(1) NOT NULL DEFAULT 0"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_pending_approval_role"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(forwards, backwards),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="user",
                    name="role",
                    field=accounts.fields.MysqlChoiceEnumField(
                        choices=ROLE_CHOICES,
                        default="PENDING_APPROVAL",
                        max_length=20,
                    ),
                ),
                migrations.AlterField(
                    model_name="user",
                    name="is_approved",
                    field=accounts.fields.MysqlBooleanEnumField(
                        default=False,
                        help_text="New employee registrations stay locked until an admin or manager approves them.",
                    ),
                ),
            ],
        ),
    ]

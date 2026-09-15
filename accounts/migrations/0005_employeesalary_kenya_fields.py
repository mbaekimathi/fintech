# Generated manually for Kenyan salary master data

from django.db import migrations, models


def copy_amount_to_basic(apps, schema_editor):
    EmployeeSalary = apps.get_model("accounts", "EmployeeSalary")
    for row in EmployeeSalary.objects.all():
        if row.basic_salary == 0 and row.amount:
            row.basic_salary = row.amount
            row.save(update_fields=["basic_salary"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_employee_salary"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeesalary",
            name="basic_salary",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="house_allowance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="transport_allowance",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="other_allowances",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="national_id",
            field=models.CharField(blank=True, max_length=20, verbose_name="national ID / passport"),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="kra_pin",
            field=models.CharField(blank=True, max_length=11, verbose_name="KRA PIN"),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="nssf_number",
            field=models.CharField(blank=True, max_length=20, verbose_name="NSSF number"),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="shif_number",
            field=models.CharField(blank=True, max_length=20, verbose_name="SHIF / SHA number"),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="is_resident",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="is_person_with_disability",
            field=models.BooleanField(default=False, verbose_name="person with disability (PWD)"),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="pwd_exemption_certificate",
            field=models.CharField(
                blank=True,
                max_length=40,
                verbose_name="PWD IT exemption certificate",
            ),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="bank_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="bank_branch",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="employeesalary",
            name="bank_account_number",
            field=models.CharField(blank=True, max_length=34),
        ),
        migrations.RunPython(copy_amount_to_basic, migrations.RunPython.noop),
    ]

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from accounts.role_switch import SESSION_KEY
from accounts.role_urls import reset_current_role_slug, set_current_role_slug

UserModel = get_user_model()


class RoleSwitchTests(TestCase):
    def setUp(self):
        self.it = UserModel.objects.create_user(
            staff_code="100001",
            password="test-pass-123",
            email="it.support@example.com",
            first_name="Kimathi",
            last_name="Mbae",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="100002",
            password="test-pass-123",
            email="employee@example.com",
            first_name="Staff",
            last_name="User",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )

    def _url(self, name, role_slug, *args):
        token = set_current_role_slug(role_slug)
        try:
            return reverse(name, args=args)
        finally:
            reset_current_role_slug(token)

    def test_it_support_can_switch_and_access_role_pages(self):
        self.client.force_login(self.it)
        it_people = self._url("accounts:users", "it-support")
        admin_people = self._url("accounts:users", "admin")
        self.assertEqual(self.client.get(it_people).status_code, 403)

        # Visiting another role's URL switches the session and opens that role's pages.
        response = self.client.get(admin_people)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get(SESSION_KEY), User.Role.ADMIN)

        response = self.client.post(reverse("accounts:switch_role"), {"role": User.Role.EMPLOYEE})
        self.assertRedirects(
            response, "/as/employee/", fetch_redirect_response=False
        )
        # Employee role cannot open People; staying on /as/employee/ keeps the switch.
        self.assertEqual(self.client.get(self._url("accounts:users", "employee")).status_code, 403)
        dash = self.client.get(self._url("core:dashboard", "employee"))
        self.assertEqual(dash.status_code, 200)
        self.assertContains(dash, "Employee")
        self.assertContains(dash, "Switch role")
        self.assertContains(dash, 'href="/as/manager/"')

    def test_menu_links_switch_away_from_employee(self):
        self.client.force_login(self.it)
        self.client.post(reverse("accounts:switch_role"), {"role": User.Role.EMPLOYEE})
        response = self.client.get("/as/manager/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get(SESSION_KEY), User.Role.MANAGER)
        self.assertContains(response, "Manager")
        self.assertContains(response, "viewing")

    def test_role_prefix_appears_in_session_pages(self):
        self.client.force_login(self.it)
        response = self.client.get("/")
        self.assertRedirects(
            response, "/as/it-support/", fetch_redirect_response=False
        )
        self.client.post(reverse("accounts:switch_role"), {"role": User.Role.MANAGER})
        response = self.client.get("/")
        self.assertRedirects(response, "/as/manager/", fetch_redirect_response=False)
        response = self.client.get("/as/manager/hr/")
        self.assertEqual(response.status_code, 200)

    def test_non_it_cannot_switch(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("accounts:switch_role"), {"role": User.Role.ADMIN})
        self.assertRedirects(
            response, self._url("core:dashboard", "employee"), fetch_redirect_response=False
        )
        self.assertIsNone(self.client.session.get(SESSION_KEY))
        self.assertEqual(self.client.get(self._url("accounts:users", "employee")).status_code, 403)

    def test_logout_clears_switch(self):
        self.client.force_login(self.it)
        self.client.post(reverse("accounts:switch_role"), {"role": User.Role.ACCOUNTS})
        self.assertEqual(self.client.session.get(SESSION_KEY), User.Role.ACCOUNTS)
        self.client.post(reverse("accounts:logout"))
        self.client.force_login(self.it)
        self.assertIsNone(self.client.session.get(SESSION_KEY))


class KenyaSalaryRegisterTests(TestCase):
    def setUp(self):
        self.hr = UserModel.objects.create_user(
            staff_code="200001",
            password="test-pass-123",
            email="hr.manager@example.com",
            first_name="Ada",
            last_name="Okello",
            role=User.Role.MANAGER,
            is_approved=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="200002",
            password="test-pass-123",
            email="paid.staff@example.com",
            first_name="Paid",
            last_name="Staff",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )

    def _url(self, name, *args):
        token = set_current_role_slug("manager")
        try:
            return reverse(name, args=args)
        finally:
            reset_current_role_slug(token)

    def test_register_page_shows_kenya_fields(self):
        self.client.force_login(self.hr)
        response = self.client.get(self._url("accounts:hr-salary-register", self.employee.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Basic salary")
        self.assertContains(response, "KRA PIN")
        self.assertContains(response, "NSSF number")
        self.assertContains(response, "SHIF / SHA number")
        self.assertContains(response, "Estimated statutory deductions")
        self.assertContains(response, "Payment method")
        self.assertContains(response, "M-Pesa")

    def test_register_persists_kenya_package(self):
        from decimal import Decimal

        from accounts.models import EmployeeSalary

        self.client.force_login(self.hr)
        response = self.client.post(
            self._url("accounts:hr-salary-register", self.employee.pk),
            {
                "basic_salary": "80000",
                "house_allowance": "15000",
                "transport_allowance": "5000",
                "other_allowances": "0",
                "currency": "KES",
                "national_id": "32109876",
                "kra_pin": "a123456789z",
                "nssf_number": "987654321",
                "shif_number": "7654321",
                "is_resident": "on",
                "payment_method": "BANK",
                "bank_name": "Equity Bank",
                "bank_branch": "Kisumu",
                "bank_account_number": "012345678901",
                "mpesa_number": "",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        salary = EmployeeSalary.objects.get(employee=self.employee)
        self.assertEqual(salary.basic_salary, Decimal("80000.00"))
        self.assertEqual(salary.amount, Decimal("100000.00"))
        self.assertEqual(salary.kra_pin, "A123456789Z")
        self.assertEqual(salary.nssf_number, "987654321")
        self.assertEqual(salary.shif_number, "7654321")
        self.assertEqual(salary.payment_method, EmployeeSalary.PaymentMethod.BANK)
        self.assertTrue(salary.is_resident)

    def test_register_mpesa_payout(self):
        from accounts.models import EmployeeSalary

        self.client.force_login(self.hr)
        response = self.client.post(
            self._url("accounts:hr-salary-register", self.employee.pk),
            {
                "basic_salary": "50000",
                "house_allowance": "0",
                "transport_allowance": "0",
                "other_allowances": "0",
                "currency": "KES",
                "national_id": "32109876",
                "kra_pin": "A123456789Z",
                "nssf_number": "987654321",
                "shif_number": "7654321",
                "is_resident": "on",
                "payment_method": "MPESA",
                "bank_name": "Equity Bank",
                "bank_branch": "Kisumu",
                "bank_account_number": "012345678901",
                "mpesa_number": "0712345678",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        salary = EmployeeSalary.objects.get(employee=self.employee)
        self.assertEqual(salary.payment_method, EmployeeSalary.PaymentMethod.MPESA)
        self.assertEqual(salary.mpesa_number, "254712345678")
        self.assertEqual(salary.bank_name, "")
        self.assertEqual(salary.bank_account_number, "")


class ProfileApprovalPasswordTests(TestCase):
    def setUp(self):
        self.reviewer = UserModel.objects.create_user(
            staff_code="600001",
            password="112233",
            email="reviewer@example.com",
            first_name="Review",
            last_name="User",
            role=User.Role.IT_SUPPORT,
            is_approved=True,
        )
        self.employee = UserModel.objects.create_user(
            staff_code="600002",
            password="445566",
            email="employee@example.com",
            first_name="Emp",
            last_name="User",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )

    def _url(self, name):
        token = set_current_role_slug("it-support")
        try:
            return reverse(name)
        finally:
            reset_current_role_slug(token)

    def test_reviewer_sees_approval_password_section(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(self._url("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approval password")
        self.assertContains(response, "Not set")
        self.assertContains(response, ">Edit</button>", count=3)
        self.assertContains(response, "••••••")

    def test_employee_without_review_permission_does_not_see_section(self):
        token = set_current_role_slug("employee")
        try:
            profile_url = reverse("accounts:profile")
        finally:
            reset_current_role_slug(token)
        self.client.force_login(self.employee)
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Approval password")

    def test_set_approval_password_must_differ_from_login_password(self):
        self.client.force_login(self.reviewer)
        response = self.client.post(
            self._url("accounts:profile"),
            {
                "action": "approval_password",
                "new_approval_password1": "112233",
                "new_approval_password2": "112233",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "must be different from your login password")
        self.reviewer.refresh_from_db()
        self.assertFalse(self.reviewer.has_approval_password)

    def test_set_and_change_approval_password(self):
        self.client.force_login(self.reviewer)
        created = self.client.post(
            self._url("accounts:profile"),
            {
                "action": "approval_password",
                "new_approval_password1": "778899",
                "new_approval_password2": "778899",
            },
        )
        self.assertRedirects(created, self._url("accounts:profile"))
        self.reviewer.refresh_from_db()
        self.assertTrue(self.reviewer.check_approval_password("778899"))
        self.assertFalse(self.reviewer.check_password("778899"))

        missing_old = self.client.post(
            self._url("accounts:profile"),
            {
                "action": "approval_password",
                "new_approval_password1": "990011",
                "new_approval_password2": "990011",
            },
        )
        self.assertEqual(missing_old.status_code, 200)
        self.assertContains(missing_old, "Enter your old approval password")

        changed = self.client.post(
            self._url("accounts:profile"),
            {
                "action": "approval_password",
                "old_approval_password": "778899",
                "new_approval_password1": "990011",
                "new_approval_password2": "990011",
            },
        )
        self.assertRedirects(changed, self._url("accounts:profile"))
        self.reviewer.refresh_from_db()
        self.assertTrue(self.reviewer.check_approval_password("990011"))

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

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import EmployeePermissions, User
from accounts.permissions import role_default_permissions, sync_permissions_from_role
from accounts.role_urls import reset_current_role_slug, set_current_role_slug

UserModel = get_user_model()


class EmployeePermissionsTests(TestCase):
    def setUp(self):
        self.hr = UserModel.objects.create_user(
            staff_code="300001",
            password="test-pass-123",
            email="hr@example.com",
            first_name="HR",
            last_name="Lead",
            role=User.Role.MANAGER,
            is_approved=True,
        )
        sync_permissions_from_role(self.hr, reset=True)
        self.employee = UserModel.objects.create_user(
            staff_code="300002",
            password="test-pass-123",
            email="staff@example.com",
            first_name="Staff",
            last_name="Member",
            role=User.Role.EMPLOYEE,
            is_approved=True,
        )
        sync_permissions_from_role(self.employee, reset=True)

    def _url(self, name, *args):
        token = set_current_role_slug("manager")
        try:
            return reverse(name, args=args)
        finally:
            reset_current_role_slug(token)

    def test_permissions_page_groups_by_role(self):
        self.client.force_login(self.hr)
        response = self.client.get(self._url("accounts:hr-permissions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Employee permissions")
        self.assertContains(response, "Manager")
        self.assertContains(response, "Employee")
        self.assertContains(response, "300002")
        self.assertContains(response, "App settings")
        self.assertContains(response, "App approval is")
        self.assertContains(response, "App on approve")
        self.assertContains(response, "PIN on approve")

    def test_toggle_permission_updates_access(self):
        self.client.force_login(self.hr)
        self.assertTrue(self.employee.can_submit_requests())
        response = self.client.post(
            self._url("accounts:hr-permission-toggle", self.employee.pk),
            {"activity": "submit_requests", "enabled": "0"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.can_submit_requests())
        perms = EmployeePermissions.objects.get(user=self.employee)
        self.assertFalse(perms.submit_requests)

    def test_toggle_pin_approval_prompt(self):
        self.client.force_login(self.hr)
        response = self.client.post(
            self._url("accounts:hr-permission-toggle", self.employee.pk),
            {"activity": "pin_approval_prompt", "enabled": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.can_pin_approval_prompt())

    def test_role_defaults(self):
        defaults = role_default_permissions(User.Role.EMPLOYEE)
        self.assertTrue(defaults["submit_requests"])
        self.assertFalse(defaults["manage_hr"])
        self.assertFalse(defaults["pin_approval_prompt"])

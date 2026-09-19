"""Workspace activity permissions (defaults by role, overrides per employee)."""

from __future__ import annotations

from accounts.models import User

ACTIVITIES: tuple[dict[str, str], ...] = (
    {
        "code": "submit_requests",
        "label": "Submit requests",
        "hint": "Raise money requests from the dashboard.",
    },
    {
        "code": "review_requests",
        "label": "Review requests",
        "hint": "Approve or reject pending money requests.",
    },
    {
        "code": "pin_approval_prompt",
        "label": "App on approve",
        "hint": "When hub app approval is on, this person must enter their separate 6-digit approval password in the app before sending a payment.",
    },
    {
        "code": "stk_pin_approval_prompt",
        "label": "PIN on approve",
        "hint": "When hub PIN approval is on, this person must complete the M-Pesa STK PIN prompt on their phone before sending a payment.",
    },
    {
        "code": "manage_app_settings",
        "label": "App settings",
        "hint": "Open App settings and configure hub-wide toggles such as app and PIN approval.",
    },
    {
        "code": "manage_people",
        "label": "Manage people",
        "hint": "Open People, approve accounts, and assign roles.",
    },
    {
        "code": "manage_hr",
        "label": "HR tools",
        "hint": "Pending approvals, employees, salaries, and this page.",
    },
    {
        "code": "manage_ledger",
        "label": "Paybills & ledger",
        "hint": "Paybill accounts, systems, and ledger operations.",
    },
    {
        "code": "manage_daraja",
        "label": "Daraja setup",
        "hint": "Configure and test M-Pesa Daraja credentials.",
    },
    {
        "code": "view_hub_balance",
        "label": "Hub balance",
        "hint": "View utility/working float and move funds on the dashboard.",
    },
    {
        "code": "manage_integrations",
        "label": "Integrations",
        "hint": "Connected systems and integration settings.",
    },
)

ACTIVITY_CODES = frozenset(item["code"] for item in ACTIVITIES)

PERMISSION_ROLE_ORDER = (
    User.Role.ADMIN,
    User.Role.MANAGER,
    User.Role.ACCOUNTS,
    User.Role.IT_SUPPORT,
    User.Role.EMPLOYEE,
)

_EMPTY = {code: False for code in ACTIVITY_CODES}

_ROLE_DEFAULTS: dict[str, dict[str, bool]] = {
    User.Role.PENDING_APPROVAL: dict(_EMPTY),
    User.Role.CLIENT: dict(_EMPTY),
    User.Role.EMPLOYEE: {
        **_EMPTY,
        "submit_requests": True,
    },
    User.Role.ACCOUNTS: {
        **_EMPTY,
        "review_requests": True,
        "manage_ledger": True,
        "view_hub_balance": True,
    },
    User.Role.IT_SUPPORT: {
        **_EMPTY,
        "review_requests": True,
        "manage_hr": True,
        "manage_ledger": True,
        "manage_daraja": True,
        "view_hub_balance": True,
        "manage_integrations": True,
        "manage_app_settings": True,
    },
    User.Role.MANAGER: {
        **_EMPTY,
        "review_requests": True,
        "manage_people": True,
        "manage_hr": True,
        "manage_ledger": True,
        "manage_daraja": True,
        "view_hub_balance": True,
        "manage_app_settings": True,
    },
    User.Role.ADMIN: {code: True for code in ACTIVITY_CODES},
}


def role_default_permissions(role: str) -> dict[str, bool]:
    return dict(_ROLE_DEFAULTS.get(role, _EMPTY))


def permission_flags_for_user(user: User) -> dict[str, bool]:
    from accounts.models import EmployeePermissions

    try:
        return user.permissions.as_flags()
    except EmployeePermissions.DoesNotExist:
        return role_default_permissions(user.role)


def activity_enabled(user: User, code: str) -> bool:
    if code not in ACTIVITY_CODES:
        return False
    return bool(permission_flags_for_user(user).get(code))


def permission_map_for_users(users) -> dict[int, dict[str, bool]]:
    user_list = list(users)
    if not user_list:
        return {}
    from accounts.models import EmployeePermissions

    records = {
        row.user_id: row
        for row in EmployeePermissions.objects.filter(user_id__in=[u.pk for u in user_list])
    }
    return {
        user.pk: (
            records[user.pk].as_flags()
            if user.pk in records
            else role_default_permissions(user.role)
        )
        for user in user_list
    }


def sync_permissions_from_role(user: User, *, reset: bool = False):
    from accounts.models import EmployeePermissions

    defaults = role_default_permissions(user.role)
    perms, created = EmployeePermissions.objects.get_or_create(user=user, defaults=defaults)
    if reset and not created:
        for key, value in defaults.items():
            setattr(perms, key, value)
        perms.save()
    return perms

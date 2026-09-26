"""Workspace activity permissions (defaults by role, overrides per employee)."""

from __future__ import annotations

from accounts.models import User

PERMISSION_GROUPS: tuple[dict[str, str], ...] = (
    {"id": "paybill", "label": "Paybill, collections & float"},
    {"id": "requests", "label": "Money requests & approvals"},
    {"id": "admin", "label": "People, HR & configuration"},
)

ACTIVITIES: tuple[dict[str, str], ...] = (
    {
        "code": "manage_ledger",
        "group": "paybill",
        "label": "Automations & ledger",
        "short_label": "Automations",
        "hint": "Automations hub (collection accounts, STK collect, C2B, partner API), transactions, and ledger.",
    },
    {
        "code": "manage_daraja",
        "group": "paybill",
        "label": "Daraja setup",
        "short_label": "Daraja",
        "hint": "Configure and test M-Pesa Daraja credentials and callbacks.",
    },
    {
        "code": "view_hub_balance",
        "group": "paybill",
        "label": "Hub balance",
        "short_label": "Balance",
        "hint": "View utility/working float and move funds on the dashboard.",
    },
    {
        "code": "submit_requests",
        "group": "requests",
        "label": "Submit requests",
        "short_label": "Submit",
        "hint": "Raise money requests from the dashboard.",
    },
    {
        "code": "review_requests",
        "group": "requests",
        "label": "Review requests",
        "short_label": "Review",
        "hint": "Approve or reject pending money requests.",
    },
    {
        "code": "pin_approval_prompt",
        "group": "requests",
        "label": "App on approve",
        "short_label": "App approve",
        "hint": "When hub app approval is on, use the in-app approval password before sending payouts.",
    },
    {
        "code": "stk_pin_approval_prompt",
        "group": "requests",
        "label": "PIN on approve",
        "short_label": "PIN approve",
        "hint": "When hub PIN approval is on, receive an M-Pesa STK prompt on the phone before sending.",
    },
    {
        "code": "manage_people",
        "group": "admin",
        "label": "Manage people",
        "short_label": "People",
        "hint": "Open People, approve accounts, and assign roles.",
    },
    {
        "code": "manage_hr",
        "group": "admin",
        "label": "HR tools",
        "short_label": "HR",
        "hint": "Pending approvals, employees, salaries, and this permissions page.",
    },
    {
        "code": "manage_app_settings",
        "group": "admin",
        "label": "App settings",
        "short_label": "App",
        "hint": "Hub-wide toggles such as app and PIN approval.",
    },
    {
        "code": "manage_integrations",
        "group": "admin",
        "label": "Integrations",
        "short_label": "API",
        "hint": "Connected systems and integration API settings.",
    },
)

ACTIVITY_CODES = frozenset(item["code"] for item in ACTIVITIES)

# IT Support: hub tools follow HR toggles even while previewing another role in the UI.
IT_SUPPORT_STORED_ACTIVITIES = frozenset(
    {
        "manage_ledger",
        "manage_hr",
        "manage_daraja",
        "manage_integrations",
        "manage_app_settings",
        "manage_people",
        "view_hub_balance",
        "review_requests",
    }
)

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
        "submit_requests": True,
        "review_requests": True,
        "pin_approval_prompt": True,
        "stk_pin_approval_prompt": True,
        "manage_ledger": True,
        "view_hub_balance": True,
    },
    User.Role.IT_SUPPORT: {
        **_EMPTY,
        "review_requests": True,
        "pin_approval_prompt": True,
        "stk_pin_approval_prompt": True,
        "manage_people": True,
        "manage_hr": True,
        "manage_ledger": True,
        "manage_daraja": True,
        "view_hub_balance": True,
        "manage_integrations": True,
        "manage_app_settings": True,
    },
    User.Role.MANAGER: {
        **_EMPTY,
        "submit_requests": True,
        "review_requests": True,
        "pin_approval_prompt": True,
        "stk_pin_approval_prompt": True,
        "manage_people": True,
        "manage_hr": True,
        "manage_ledger": True,
        "manage_daraja": True,
        "view_hub_balance": True,
        "manage_app_settings": True,
    },
    User.Role.ADMIN: {code: True for code in ACTIVITY_CODES},
}


def activities_by_group() -> list[dict]:
    grouped: dict[str, list[dict]] = {g["id"]: [] for g in PERMISSION_GROUPS}
    for activity in ACTIVITIES:
        grouped.setdefault(activity["group"], []).append(activity)
    return [
        {"group": group, "activities": grouped.get(group["id"], [])}
        for group in PERMISSION_GROUPS
        if grouped.get(group["id"])
    ]


def role_default_permissions(role: str) -> dict[str, bool]:
    return dict(_ROLE_DEFAULTS.get(role, _EMPTY))


def ensure_employee_permissions(user: User):
    """Create or lift permissions to role defaults (True-only) for stale rows."""
    from accounts.models import EmployeePermissions

    defaults = role_default_permissions(user.role)
    perms, created = EmployeePermissions.objects.get_or_create(user=user, defaults=defaults)
    if created:
        return perms
    update_fields: list[str] = []
    for code, should_on in defaults.items():
        if should_on and not getattr(perms, code):
            setattr(perms, code, True)
            update_fields.append(code)
    if update_fields:
        update_fields.append("updated_at")
        perms.save(update_fields=update_fields)
    return perms


def permission_flags_for_user(user: User) -> dict[str, bool]:
    from accounts.models import EmployeePermissions

    try:
        perms = user.permissions
        perms.refresh_from_db()
        return perms.as_flags()
    except EmployeePermissions.DoesNotExist:
        return role_default_permissions(user.role)


def activity_enabled(user: User, code: str) -> bool:
    if code not in ACTIVITY_CODES:
        return False
    db_on = bool(permission_flags_for_user(user).get(code))
    if user.role == User.Role.IT_SUPPORT and code in IT_SUPPORT_STORED_ACTIVITIES:
        return db_on
    if getattr(user, "is_role_switched", False):
        return bool(role_default_permissions(user.effective_role).get(code))
    return db_on


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

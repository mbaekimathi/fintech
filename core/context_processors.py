from accounts.models import User
from accounts.role_switch import SWITCHABLE_ROLES
from accounts.role_urls import role_to_slug, workspace_url
from core.models import AppSettings
from core.notifications import unread_notification_count, user_notifications
from core.webpush import vapid_public_key, webpush_enabled

GLOBAL_NAV = {"name": "Dashboard", "url": "core:dashboard", "icon": "grid"}
DARAJA_NAV = [
    {"name": "Daraja setup", "url": "core:daraja", "icon": "key"},
    {"name": "Test credentials", "url": "core:daraja-test", "icon": "flow"},
]
DARAJA_URLS = {item["url"] for item in DARAJA_NAV}
SETTINGS_NAV = [
    {"name": "App settings", "url": "core:app-settings", "icon": "gear"},
]
SETTINGS_URLS = {"core:settings", "core:app-settings"}
HR_NAV = [
    {"name": "Pending approvals", "url": "accounts:hr-pending", "icon": "people"},
    {"name": "Employee management", "url": "accounts:hr-employees", "icon": "people"},
    {"name": "Employee permissions", "url": "accounts:hr-permissions", "icon": "people"},
    {"name": "Employee salaries", "url": "accounts:hr-salaries", "icon": "card"},
]
HR_URLS = {
    "accounts:hr",
    "accounts:hr-pending",
    "accounts:hr-employees",
    "accounts:hr-employee-edit",
    "accounts:hr-permissions",
    "accounts:hr-salaries",
    "accounts:hr-salary-register",
    "accounts:hr-salary-update",
}


def _section_items(user):
    items = [
        {"name": "Transactions", "url": "paybill:transactions", "icon": "flow"},
    ]
    if user.can_manage_ledger():
        items.append({"name": "Paybills", "url": "paybill:accounts", "icon": "card"})
        items.append({"name": "Systems", "url": "paybill:systems", "icon": "nodes"})
    if user.can_manage_users():
        items.append({"name": "People", "url": "accounts:users", "icon": "people"})
    if user.can_manage_hr():
        items.append({"name": "HR", "url": "accounts:hr", "icon": "people"})
    return items


def shell(request):
    user = getattr(request, "user", None)
    nav = []
    switchable_roles = ()
    header_notifications = []
    unread_count = 0
    can_review_money_requests = False
    can_manage_app_settings = False
    pin_approval_required = False
    pin_approval_required_for_user = False
    if user and user.is_authenticated and not user.is_pending:
        current = getattr(getattr(request, "resolver_match", None), "view_name", "")
        sections = _section_items(user)
        nav = [GLOBAL_NAV]
        can_manage_app_settings = user.can_manage_app_settings() or (
            user.is_superuser and not user.is_role_switched
        )
        pin_approval_required = AppSettings.load().pin_approval_required
        pin_approval_required_for_user = user.requires_pin_on_approval()
        # Dashboard is the hub: show every section the role can open.
        # Other pages keep only their own section link. System settings and
        # log out stay in the sidebar footer on every page. Daraja setup expands
        # into one sidebar link per logic page. HR expands into its tools.
        if current in SETTINGS_URLS:
            if can_manage_app_settings:
                nav.extend(SETTINGS_NAV)
            if user.can_manage_daraja():
                nav.extend(DARAJA_NAV)
        elif current in DARAJA_URLS and user.can_manage_daraja():
            nav.extend(DARAJA_NAV)
        elif current in HR_URLS and user.can_manage_hr():
            nav.append({"name": "HR", "url": "accounts:hr", "icon": "people"})
            nav.extend(HR_NAV)
        elif current == GLOBAL_NAV["url"]:
            nav.extend(sections)
        else:
            nav.extend(item for item in sections if item["url"] == current)
        if user.can_switch_roles():
            switchable_roles = tuple(
                {
                    "value": value,
                    "label": label,
                    "href": workspace_url("/", value),
                    "slug": role_to_slug(value),
                }
                for value, label in SWITCHABLE_ROLES
            )
        header_notifications = list(user_notifications(user))
        unread_count = unread_notification_count(user)
        can_review_money_requests = user.can_review_requests()
    return {
        "product_name": "NEXUS",
        "product_tag": "Financial architecture",
        "nav_items": nav,
        "role_choices": User.Role.choices,
        "switchable_roles": switchable_roles,
        "header_notifications": header_notifications,
        "unread_notification_count": unread_count,
        "can_review_money_requests": can_review_money_requests,
        "can_manage_app_settings": can_manage_app_settings,
        "pin_approval_required": pin_approval_required,
        "pin_approval_required_for_user": pin_approval_required_for_user,
        "webpush_enabled": webpush_enabled(),
        "webpush_vapid_public_key": vapid_public_key() if webpush_enabled() else "",
    }

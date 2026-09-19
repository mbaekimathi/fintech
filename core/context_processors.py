from accounts.models import User
from accounts.role_switch import SWITCHABLE_ROLES
from accounts.role_urls import get_current_role_slug, role_to_slug, workspace_url
from django.urls import reverse
from django.conf import settings as django_settings

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
    app_approval_required = False
    stk_pin_approval_required = False
    app_approval_required_for_user = False
    stk_pin_approval_required_for_user = False
    approval_stk_poll_url_base = ""
    reviewer_has_approval_password = False
    profile_url = ""
    if user and user.is_authenticated and not user.is_pending:
        current = getattr(getattr(request, "resolver_match", None), "view_name", "")
        sections = _section_items(user)
        nav = [GLOBAL_NAV]
        can_manage_app_settings = user.can_manage_app_settings() or (
            user.is_superuser and not user.is_role_switched
        )
        settings = AppSettings.load()
        app_approval_required = settings.app_approval_required
        stk_pin_approval_required = settings.stk_pin_approval_required
        app_approval_required_for_user = user.requires_app_on_approval()
        stk_pin_approval_required_for_user = user.requires_stk_on_approval()
        reviewer_has_approval_password = user.has_approval_password
        profile_url = reverse("accounts:profile")
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
        if can_review_money_requests and get_current_role_slug():
            approval_stk_poll_url_base = reverse(
                "core:approval-stk-poll",
                kwargs={"pk": 0},
            ).replace("/0/", "/")
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
        "app_approval_required": app_approval_required,
        "stk_pin_approval_required": stk_pin_approval_required,
        "app_approval_required_for_user": app_approval_required_for_user,
        "stk_pin_approval_required_for_user": stk_pin_approval_required_for_user,
        "approval_stk_poll_url_base": approval_stk_poll_url_base,
        "reviewer_has_approval_password": reviewer_has_approval_password,
        "profile_url": profile_url,
        "webpush_enabled": webpush_enabled(),
        "webpush_vapid_public_key": vapid_public_key() if webpush_enabled() else "",
        "asset_version": getattr(django_settings, "ASSET_VERSION", ""),
    }

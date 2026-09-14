from accounts.models import User

GLOBAL_NAV = {"name": "Dashboard", "url": "core:dashboard", "icon": "grid"}
DARAJA_NAV = {"name": "Daraja", "url": "core:daraja", "icon": "key"}
TEST_NAV = {"name": "Test credentials", "url": "core:daraja-test", "icon": "flow"}


def _section_items(user):
    items = [
        {"name": "Transactions", "url": "paybill:transactions", "icon": "flow"},
    ]
    if user.can_manage_ledger() or user.role == User.Role.IT_SUPPORT:
        items.append({"name": "Paybills", "url": "paybill:accounts", "icon": "card"})
        items.append({"name": "Systems", "url": "paybill:systems", "icon": "nodes"})
    if user.can_manage_users():
        items.append({"name": "People", "url": "accounts:users", "icon": "people"})
    return items


def shell(request):
    user = getattr(request, "user", None)
    nav = []
    if user and user.is_authenticated and not user.is_pending:
        current = getattr(getattr(request, "resolver_match", None), "view_name", "")
        sections = _section_items(user)
        nav = [GLOBAL_NAV]
        # Dashboard is the hub: show every section the role can open.
        # Other pages keep only their own section link. System settings and
        # log out stay in the sidebar footer on every page. Daraja setup sits
        # under Dashboard on System settings only.
        if current in {"core:settings", "core:daraja", "core:daraja-test"} and user.can_manage_daraja():
            nav.append(DARAJA_NAV)
            if current in {"core:daraja", "core:daraja-test"}:
                nav.append(TEST_NAV)
        elif current == GLOBAL_NAV["url"]:
            nav.extend(sections)
        else:
            nav.extend(item for item in sections if item["url"] == current)
    return {
        "product_name": "NEXUS",
        "product_tag": "Ledger hub",
        "nav_items": nav,
        "role_choices": User.Role.choices,
    }

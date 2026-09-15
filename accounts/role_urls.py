"""Role-prefixed workspace URLs: /as/<role-slug>/page.

Incoming /as/<slug>/... is stripped before URL resolve. reverse() and {% url %}
re-apply the prefix for workspace routes (same idea as i18n language prefixes).
"""

from __future__ import annotations

from contextvars import ContextVar

from django.urls import reverse as django_reverse
from django.urls import base as urls_base

from accounts.models import User

ROLE_TO_SLUG = {
    User.Role.ADMIN: "admin",
    User.Role.MANAGER: "manager",
    User.Role.EMPLOYEE: "employee",
    User.Role.CLIENT: "client",
    User.Role.ACCOUNTS: "accounts",
    User.Role.IT_SUPPORT: "it-support",
}
SLUG_TO_ROLE = {slug: role for role, slug in ROLE_TO_SLUG.items()}
ROLE_PREFIX = "as"

_current_role_slug: ContextVar[str | None] = ContextVar("current_role_slug", default=None)
_patch_installed = False

# Named routes that stay outside /as/<role>/.
UNPREFIXED_URL_NAMES = {
    "accounts:login",
    "accounts:logout",
    "accounts:switch_role",
    "accounts:register",
    "accounts:register_done",
    "accounts:pending",
    "core:service-worker",
    "core:web-manifest",
}

UNPREFIXED_PATH_PREFIXES = (
    "/admin/",
    "/api/",
    "/static/",
    "/login/",
    "/logout/",
    "/register/",
    "/pending/",
    "/switch-role/",
    "/sw.js",
    "/manifest.webmanifest",
)


def role_to_slug(role: str | None) -> str | None:
    if not role:
        return None
    return ROLE_TO_SLUG.get(role)


def slug_to_role(slug: str | None) -> str | None:
    if not slug:
        return None
    return SLUG_TO_ROLE.get(slug)


def set_current_role_slug(slug: str | None):
    return _current_role_slug.set(slug)


def reset_current_role_slug(token) -> None:
    _current_role_slug.reset(token)


def get_current_role_slug() -> str | None:
    return _current_role_slug.get()


def parse_role_prefix(path: str) -> tuple[str | None, str]:
    """Return (role_slug, remainder_path) when path is /as/<slug>/..."""
    if not path.startswith(f"/{ROLE_PREFIX}/"):
        return None, path
    rest = path[len(ROLE_PREFIX) + 2 :]
    if not rest:
        return None, path
    slug, sep, remainder = rest.partition("/")
    if slug not in SLUG_TO_ROLE:
        return None, path
    if sep:
        return slug, "/" + remainder
    return slug, "/"


def is_unprefixed_path(path: str) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p) for p in UNPREFIXED_PATH_PREFIXES)


def workspace_url(path: str, role: str | None) -> str:
    """Build /as/<slug>/<path> for a role value (ADMIN) or slug (admin)."""
    slug = role_to_slug(role) if role and role in ROLE_TO_SLUG else role
    if slug not in SLUG_TO_ROLE:
        slug = ROLE_TO_SLUG[User.Role.EMPLOYEE]
    if not path.startswith("/"):
        path = "/" + path
    if path == "/":
        return f"/{ROLE_PREFIX}/{slug}/"
    return f"/{ROLE_PREFIX}/{slug}{path}"


def _should_prefix(viewname: str | None, url: str) -> bool:
    if not viewname or viewname in UNPREFIXED_URL_NAMES:
        return False
    if is_unprefixed_path(url):
        return False
    if url.startswith(f"/{ROLE_PREFIX}/"):
        return False
    return True


def reverse(viewname, urlconf=None, args=None, kwargs=None, current_app=None):
    url = django_reverse(viewname, urlconf=urlconf, args=args, kwargs=kwargs, current_app=current_app)
    slug = get_current_role_slug()
    if slug and _should_prefix(viewname if isinstance(viewname, str) else None, url):
        if url == "/":
            return f"/{ROLE_PREFIX}/{slug}/"
        return f"/{ROLE_PREFIX}/{slug}{url}"
    return url


def install_role_reverse_patch() -> None:
    """Patch django.urls.reverse so {% url %} and reverse() add /as/<role>/."""
    global _patch_installed
    if _patch_installed:
        return
    urls_base.reverse = reverse
    import django.urls as urls_module
    import django.shortcuts as shortcuts_module

    urls_module.reverse = reverse
    shortcuts_module.reverse = reverse
    _patch_installed = True

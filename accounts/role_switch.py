"""Session-only role switch for IT Support (does not change the stored User.role)."""

from __future__ import annotations

from accounts.models import User

SESSION_KEY = "view_as_role"

SWITCHABLE_ROLES = tuple(
    choice for choice in User.Role.choices if choice[0] != User.Role.PENDING_APPROVAL
)
SWITCHABLE_ROLE_VALUES = {value for value, _label in SWITCHABLE_ROLES}


def can_use_role_switch(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and user.role == User.Role.IT_SUPPORT
    )


def get_session_view_as_role(request) -> str | None:
    value = request.session.get(SESSION_KEY)
    if value in SWITCHABLE_ROLE_VALUES:
        return value
    return None


def apply_role_switch(user, view_as_role: str | None) -> None:
    """Attach effective role onto the user instance for this request only."""
    if view_as_role and view_as_role in SWITCHABLE_ROLE_VALUES:
        user._effective_role = view_as_role
    else:
        user.__dict__.pop("_effective_role", None)


def set_view_as_role(request, role: str) -> str:
    if role not in SWITCHABLE_ROLE_VALUES:
        raise ValueError("Unknown role.")
    if role == request.user.role:
        clear_view_as_role(request)
        return role
    request.session[SESSION_KEY] = role
    apply_role_switch(request.user, role)
    return role


def clear_view_as_role(request) -> None:
    request.session.pop(SESSION_KEY, None)
    if getattr(request, "user", None) and request.user.is_authenticated:
        apply_role_switch(request.user, None)

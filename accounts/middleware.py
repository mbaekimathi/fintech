from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse

from accounts.role_switch import (
    SESSION_KEY,
    apply_role_switch,
    can_use_role_switch,
    get_session_view_as_role,
    set_view_as_role,
)
from accounts.role_urls import (
    is_unprefixed_path,
    parse_role_prefix,
    reset_current_role_slug,
    role_to_slug,
    set_current_role_slug,
    slug_to_role,
    workspace_url,
)


class ApprovalGateMiddleware:
    """Signed-in but unapproved users can only reach the pending page and logout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.is_pending:
            allowed = {
                reverse("accounts:pending"),
                reverse("accounts:logout"),
            }
            if request.path not in allowed and not request.path.startswith("/admin/"):
                return redirect("accounts:pending")
        return self.get_response(request)


class RoleSwitchMiddleware:
    """Apply session role switch, expose /as/<role>/pages, and set reverse prefix."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path_slug, remainder = parse_role_prefix(request.path)
        token = set_current_role_slug(None)
        original_path_info = request.path_info

        try:
            if user and user.is_authenticated and can_use_role_switch(user):
                if path_slug:
                    role = slug_to_role(path_slug)
                    if role:
                        set_view_as_role(request, role)
                view_as = get_session_view_as_role(request)
                if request.session.get(SESSION_KEY) and view_as is None:
                    request.session.pop(SESSION_KEY, None)
                apply_role_switch(user, view_as)
            elif user and user.is_authenticated and request.session.get(SESSION_KEY):
                request.session.pop(SESSION_KEY, None)
                apply_role_switch(user, None)

            if user and user.is_authenticated and not user.is_pending:
                expected = role_to_slug(user.effective_role)
                reset_current_role_slug(token)
                token = set_current_role_slug(expected)

                if path_slug and path_slug != expected:
                    target = workspace_url(remainder, user.effective_role)
                    if request.META.get("QUERY_STRING"):
                        target = f"{target}?{request.META['QUERY_STRING']}"
                    return HttpResponseRedirect(target)

                if path_slug:
                    # Resolve the unprefixed path while keeping /as/<role>/ in the browser.
                    request.path_info = remainder
                elif not is_unprefixed_path(request.path):
                    target = workspace_url(request.path, user.effective_role)
                    if request.META.get("QUERY_STRING"):
                        target = f"{target}?{request.META['QUERY_STRING']}"
                    return HttpResponseRedirect(target)
            elif path_slug:
                # Anonymous/pending: resolve the real page (login_required still applies).
                request.path_info = remainder

            response = self.get_response(request)
            return response
        finally:
            request.path_info = original_path_info
            reset_current_role_slug(token)

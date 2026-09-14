from django.shortcuts import redirect
from django.urls import reverse


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

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class ApprovedRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_pending:
            raise PermissionDenied("Your account is waiting for approval.")
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(ApprovedRequiredMixin, UserPassesTestMixin):
    allowed_roles: tuple[str, ...] = ()

    def test_func(self):
        user = self.request.user
        if user.is_superuser and not user.is_role_switched:
            return True
        return user.effective_role in self.allowed_roles

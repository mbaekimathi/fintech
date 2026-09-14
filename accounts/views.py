from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import FormView, ListView

from accounts.forms import EmployeeRegisterForm, LoginForm
from accounts.mixins import RoleRequiredMixin
from accounts.models import User
from accounts.utils import client_ip, write_audit


class LoginView(FormView):
    template_name = "accounts/login.html"
    form_class = LoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)
        user.last_login_ip = client_ip(self.request)
        user.save(update_fields=["last_login_ip"])
        write_audit(self.request, "login.success", object_type="user", object_id=user.pk)
        return redirect("core:dashboard")

    def form_invalid(self, form):
        write_audit(self.request, "login.failed", detail={"errors": list(form.non_field_errors())})
        return super().form_invalid(form)


class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = EmployeeRegisterForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        write_audit(
            self.request,
            "register.employee",
            object_type="user",
            object_id=user.pk,
            detail={"staff_code": user.staff_code},
        )
        self.request.session["pending_staff_code"] = user.staff_code
        return redirect("accounts:register_done")


def register_done(request):
    staff_code = request.session.pop("pending_staff_code", None)
    if not staff_code:
        return redirect("accounts:register")
    return render(request, "accounts/register_done.html", {"staff_code": staff_code})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        write_audit(request, "logout", object_type="user", object_id=request.user.pk)
    logout(request)
    return redirect("accounts:login")


@login_required
def pending_view(request):
    if not request.user.is_pending:
        return redirect("core:dashboard")
    return render(request, "accounts/pending.html")


class UserDirectoryView(RoleRequiredMixin, ListView):
    template_name = "accounts/users.html"
    context_object_name = "people"
    allowed_roles = (User.Role.ADMIN, User.Role.MANAGER)
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.all().select_related("approved_by")
        status = self.request.GET.get("status")
        if status == "pending":
            qs = qs.filter(Q(is_approved=False) | Q(role=User.Role.PENDING_APPROVAL), is_active=True)
        elif status == "active":
            qs = qs.filter(is_approved=True, is_active=True).exclude(role=User.Role.PENDING_APPROVAL)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pending_count"] = (
            User.objects.filter(is_active=True)
            .filter(Q(is_approved=False) | Q(role=User.Role.PENDING_APPROVAL))
            .count()
        )
        context["approval_choices"] = (
            (True, "Approved"),
            (False, "Pending approval"),
        )
        context["status"] = self.request.GET.get("status", "all")
        return context


@login_required
@require_POST
def approve_user(request, pk):
    return _set_user_approval(request, pk, approved=True)


@login_required
@require_POST
def set_approval(request, pk):
    raw = str(request.POST.get("is_approved", "")).strip().lower()
    if raw not in {"1", "0", "true", "false"}:
        messages.error(request, "Unknown approval status.")
        return redirect("accounts:users")
    return _set_user_approval(request, pk, approved=raw in {"1", "true"})


def _set_user_approval(request, pk, *, approved: bool):
    if not request.user.can_manage_users():
        messages.error(request, "You do not have permission to change approval.")
        return redirect("core:dashboard")
    person = get_object_or_404(User, pk=pk)
    if person == request.user and not approved:
        messages.error(request, "You cannot revoke approval on your own account.")
        return redirect("accounts:users")
    update_fields = person.apply_approval(approved, actor=request.user)
    person.save(update_fields=update_fields)
    write_audit(
        request,
        "user.approve" if approved else "user.unapprove",
        object_type="user",
        object_id=person.pk,
        detail={"is_approved": approved},
    )
    status = "approved" if approved else "pending approval"
    messages.success(request, f"{person.staff_code} is now {status}.")
    return redirect("accounts:users")


@login_required
@require_POST
def set_role(request, pk):
    if not request.user.can_manage_users():
        messages.error(request, "You do not have permission to change roles.")
        return redirect("core:dashboard")
    person = get_object_or_404(User, pk=pk)
    role = request.POST.get("role")
    if role not in User.Role.values:
        messages.error(request, "Unknown role.")
        return redirect("accounts:users")
    if person == request.user and role != User.Role.ADMIN and request.user.role == User.Role.ADMIN:
        messages.error(request, "You cannot demote your own admin account.")
        return redirect("accounts:users")
    person.role = role
    if role == User.Role.ADMIN:
        person.is_staff = True
    person.save(update_fields=["role", "is_staff"])
    write_audit(request, "user.role_change", object_type="user", object_id=person.pk, detail={"role": role})
    messages.success(request, f"{person.staff_code} is now {person.get_role_display()}.")
    return redirect("accounts:users")

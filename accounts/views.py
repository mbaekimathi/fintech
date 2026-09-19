from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView

from accounts.forms import (
    EmployeeEditForm,
    EmployeeRegisterForm,
    EmployeeSalaryForm,
    LoginForm,
    ProfileApprovalPasswordForm,
    ProfileForm,
    ProfilePasswordForm,
)
from accounts.mixins import ApprovedRequiredMixin, RoleRequiredMixin
from accounts.models import EmployeeSalary, User
from accounts.role_switch import clear_view_as_role, set_view_as_role
from accounts.role_urls import role_to_slug, set_current_role_slug, workspace_url
from accounts.utils import client_ip, write_audit

HR_ROLES = (User.Role.ADMIN, User.Role.MANAGER, User.Role.IT_SUPPORT)
ASSIGNABLE_ROLES = tuple(
    choice for choice in User.Role.choices if choice[0] != User.Role.PENDING_APPROVAL
)


def _safe_next(request, fallback: str) -> str:
    candidate = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return fallback


class LoginView(FormView):
    template_name = "accounts/login.html"
    form_class = LoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            set_current_role_slug(role_to_slug(request.user.effective_role))
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
        set_current_role_slug(role_to_slug(user.role))
        return redirect("core:dashboard")

    def form_invalid(self, form):
        write_audit(self.request, "login.failed", detail={"errors": list(form.non_field_errors())})
        return super().form_invalid(form)


class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = EmployeeRegisterForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            set_current_role_slug(role_to_slug(request.user.effective_role))
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
        # Drop this user's browser push bindings so the next session user on a
        # shared device does not receive the previous employee's tray alerts.
        from core.models import PushSubscription

        PushSubscription.objects.filter(user=request.user).delete()
    clear_view_as_role(request)
    logout(request)
    return redirect("accounts:login")


@login_required
@require_POST
def switch_role(request):
    if not request.user.can_switch_roles():
        messages.error(request, "Only IT Support can switch roles.")
        return HttpResponseRedirect(workspace_url("/", request.user.effective_role))

    role = (request.POST.get("role") or "").strip()
    try:
        set_view_as_role(request, role)
    except ValueError:
        messages.error(request, "Unknown role.")
        return HttpResponseRedirect(workspace_url("/", request.user.effective_role))

    write_audit(
        request,
        "session.role_switch",
        object_type="user",
        object_id=request.user.pk,
        detail={"view_as_role": role, "stored_role": request.user.role},
    )
    messages.success(request, f"Viewing as {request.user.role_label}.")
    # Build the URL from the chosen role so reverse ContextVar state cannot
    # keep the browser on the previous /as/<role>/ workspace.
    return HttpResponseRedirect(workspace_url("/", role))


@login_required
def pending_view(request):
    if not request.user.is_pending:
        set_current_role_slug(role_to_slug(request.user.effective_role))
        return redirect("core:dashboard")
    return render(request, "accounts/pending.html")


class ProfileView(ApprovedRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = User.objects.get(pk=self.request.user.pk)
        profile_form = kwargs.get("profile_form") or ProfileForm(instance=user)
        password_form = kwargs.get("password_form") or ProfilePasswordForm(user=user)
        context["profile_user"] = user
        context["profile_form"] = profile_form
        context["password_form"] = password_form
        context["can_review_requests"] = user.can_review_requests()
        context["has_approval_password"] = user.has_approval_password
        context["edit_profile"] = bool(profile_form.errors)
        context["edit_password"] = bool(password_form.errors)
        context["edit_approval_password"] = False
        if user.can_review_requests():
            approval_password_form = (
                kwargs.get("approval_password_form") or ProfileApprovalPasswordForm(user=user)
            )
            context["approval_password_form"] = approval_password_form
            context["edit_approval_password"] = bool(approval_password_form.errors)
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        action = request.POST.get("action")

        if action == "profile":
            form = ProfileForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
                write_audit(
                    request,
                    "profile.update",
                    object_type="user",
                    object_id=user.pk,
                )
                messages.success(request, "Profile updated.")
                return redirect("accounts:profile")
            return self.render_to_response(self.get_context_data(profile_form=form))

        if action == "password":
            form = ProfilePasswordForm(user=user, data=request.POST)
            if form.is_valid():
                user.set_password(form.cleaned_data["new_password1"])
                user.save(update_fields=["password"])
                update_session_auth_hash(request, user)
                write_audit(
                    request,
                    "profile.password_change",
                    object_type="user",
                    object_id=user.pk,
                )
                messages.success(request, "Password updated.")
                return redirect("accounts:profile")
            return self.render_to_response(self.get_context_data(password_form=form))

        if action == "approval_password":
            user = User.objects.get(pk=user.pk)
            if not user.can_review_requests():
                messages.error(request, "You do not have permission to set an approval password.")
                return redirect("accounts:profile")
            form = ProfileApprovalPasswordForm(user=user, data=request.POST)
            if form.is_valid():
                user.set_approval_password(form.cleaned_data["new_approval_password1"])
                user.save(update_fields=["approval_password"])
                write_audit(
                    request,
                    "profile.approval_password_change",
                    object_type="user",
                    object_id=user.pk,
                )
                messages.success(request, "Approval password updated.")
                return redirect("accounts:profile")
            return self.render_to_response(self.get_context_data(approval_password_form=form))

        return redirect("accounts:profile")


class UserDirectoryView(RoleRequiredMixin, ListView):
    template_name = "accounts/users.html"
    context_object_name = "people"
    required_activity = "manage_people"
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


class HRView(RoleRequiredMixin, ListView):
    template_name = "accounts/hr.html"
    context_object_name = "employees"
    required_activity = "manage_hr"
    paginate_by = 25

    def get_queryset(self):
        return (
            User.objects.filter(is_active=True)
            .exclude(role__in=[User.Role.CLIENT, User.Role.PENDING_APPROVAL])
            .order_by("staff_code")
        )


class HRPendingApprovalsView(RoleRequiredMixin, ListView):
    template_name = "accounts/hr_pending.html"
    context_object_name = "people"
    required_activity = "manage_hr"
    paginate_by = 25

    def get_queryset(self):
        return (
            User.objects.filter(is_active=True)
            .filter(Q(is_approved=False) | Q(role=User.Role.PENDING_APPROVAL))
            .select_related("approved_by")
            .order_by("staff_code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assignable_roles"] = ASSIGNABLE_ROLES
        return context


class HREmployeeManagementView(RoleRequiredMixin, ListView):
    template_name = "accounts/hr_employees.html"
    context_object_name = "employees"
    required_activity = "manage_hr"
    paginate_by = 25

    def get_queryset(self):
        return User.objects.exclude(role=User.Role.CLIENT).order_by("staff_code")


class HREmployeeEditView(RoleRequiredMixin, UpdateView):
    template_name = "accounts/hr_employee_edit.html"
    form_class = EmployeeEditForm
    context_object_name = "employee"
    required_activity = "manage_hr"
    success_url = reverse_lazy("accounts:hr-employees")

    def get_queryset(self):
        return User.objects.exclude(role=User.Role.CLIENT)

    def form_valid(self, form):
        response = super().form_valid(form)
        write_audit(
            self.request,
            "hr.employee.update",
            object_type="user",
            object_id=self.object.pk,
            detail={"staff_code": self.object.staff_code},
        )
        messages.success(self.request, f"Updated {self.object.staff_code}.")
        return response


class HREmployeePermissionsView(RoleRequiredMixin, TemplateView):
    template_name = "accounts/hr_permissions.html"
    required_activity = "manage_hr"

    def get_queryset(self):
        return (
            User.objects.exclude(role=User.Role.CLIENT)
            .exclude(role=User.Role.PENDING_APPROVAL)
            .select_related("permissions")
            .order_by("staff_code")
        )

    def get_context_data(self, **kwargs):
        from collections import defaultdict

        from accounts.permissions import ACTIVITIES, PERMISSION_ROLE_ORDER, permission_map_for_users

        context = super().get_context_data(**kwargs)
        employees = list(self.get_queryset())
        flags_by_user = permission_map_for_users(employees)
        grouped: dict[str, list] = defaultdict(list)
        for person in employees:
            flags = flags_by_user.get(person.pk, {})
            person.permission_rows = [
                {
                    "code": activity["code"],
                    "label": activity["label"],
                    "enabled": flags.get(activity["code"], False),
                    "hint": activity["hint"],
                }
                for activity in ACTIVITIES
            ]
            grouped[person.role].append(person)
        context["role_groups"] = [
            {
                "role": role,
                "label": User.Role(role).label,
                "employees": grouped[role],
            }
            for role in PERMISSION_ROLE_ORDER
            if grouped.get(role)
        ]
        context["activities"] = ACTIVITIES
        from core.models import AppSettings

        app_settings = AppSettings.load()
        context["app_approval_required"] = app_settings.app_approval_required
        context["stk_pin_approval_required"] = app_settings.stk_pin_approval_required
        context["can_manage_app_settings"] = self.request.user.can_manage_app_settings()
        return context


def _active_staff_qs():
    return (
        User.objects.filter(is_active=True)
        .exclude(role__in=[User.Role.CLIENT, User.Role.PENDING_APPROVAL])
        .order_by("staff_code")
    )


class HRSalariesView(RoleRequiredMixin, ListView):
    template_name = "accounts/hr_salaries.html"
    context_object_name = "employees"
    required_activity = "manage_hr"
    paginate_by = 25

    def get_queryset(self):
        return _active_staff_qs().select_related("salary")


class HRSalaryRegisterView(RoleRequiredMixin, CreateView):
    template_name = "accounts/hr_salary_form.html"
    form_class = EmployeeSalaryForm
    required_activity = "manage_hr"
    success_url = reverse_lazy("accounts:hr-salaries")

    def dispatch(self, request, *args, **kwargs):
        self.employee = get_object_or_404(_active_staff_qs(), pk=kwargs["pk"])
        if EmployeeSalary.objects.filter(employee=self.employee).exists():
            messages.info(request, f"{self.employee.staff_code} already has a salary. Update it instead.")
            return redirect("accounts:hr-salary-update", pk=self.employee.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee"] = self.employee
        context["mode"] = "register"
        return context

    def form_valid(self, form):
        form.instance.employee = self.employee
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        write_audit(
            self.request,
            "hr.salary.register",
            object_type="employee_salary",
            object_id=self.object.pk,
            detail={
                "staff_code": self.employee.staff_code,
                "basic_salary": str(self.object.basic_salary),
                "amount": str(self.object.amount),
                "kra_pin": self.object.kra_pin,
            },
        )
        messages.success(self.request, f"Registered salary for {self.employee.staff_code}.")
        return response


class HRSalaryUpdateView(RoleRequiredMixin, UpdateView):
    template_name = "accounts/hr_salary_form.html"
    form_class = EmployeeSalaryForm
    context_object_name = "salary"
    required_activity = "manage_hr"
    success_url = reverse_lazy("accounts:hr-salaries")

    def dispatch(self, request, *args, **kwargs):
        self.employee = get_object_or_404(_active_staff_qs(), pk=kwargs["pk"])
        if not EmployeeSalary.objects.filter(employee=self.employee).exists():
            messages.info(request, f"{self.employee.staff_code} has no salary yet. Register it first.")
            return redirect("accounts:hr-salary-register", pk=self.employee.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(EmployeeSalary, employee=self.employee)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["employee"] = self.employee
        context["mode"] = "update"
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        write_audit(
            self.request,
            "hr.salary.update",
            object_type="employee_salary",
            object_id=self.object.pk,
            detail={
                "staff_code": self.employee.staff_code,
                "basic_salary": str(self.object.basic_salary),
                "amount": str(self.object.amount),
                "kra_pin": self.object.kra_pin,
            },
        )
        messages.success(self.request, f"Updated salary for {self.employee.staff_code}.")
        return response


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
        return redirect(_safe_next(request, reverse("accounts:users")))
    return _set_user_approval(request, pk, approved=raw in {"1", "true"})


def _set_user_approval(request, pk, *, approved: bool):
    fallback = reverse("accounts:users")
    next_url = _safe_next(request, fallback)
    if not (request.user.can_manage_users() or request.user.can_manage_hr()):
        messages.error(request, "You do not have permission to change approval.")
        return redirect("core:dashboard")
    person = get_object_or_404(User, pk=pk)
    if person == request.user and not approved:
        messages.error(request, "You cannot revoke approval on your own account.")
        return redirect(next_url)
    update_fields = person.apply_approval(approved, actor=request.user)
    role = request.POST.get("role")
    if approved and role and role in User.Role.values and role != User.Role.PENDING_APPROVAL:
        person.role = role
        if role == User.Role.ADMIN:
            person.is_staff = True
            update_fields = list({*update_fields, "role", "is_staff"})
        else:
            update_fields = list({*update_fields, "role"})
    person.save(update_fields=update_fields)
    if approved:
        from accounts.permissions import sync_permissions_from_role

        sync_permissions_from_role(person, reset=True)
    write_audit(
        request,
        "user.approve" if approved else "user.unapprove",
        object_type="user",
        object_id=person.pk,
        detail={"is_approved": approved, "role": person.role},
    )
    status = "approved" if approved else "pending approval"
    messages.success(request, f"{person.staff_code} is now {status}.")
    return redirect(next_url)


@login_required
@require_POST
def set_role(request, pk):
    fallback = reverse("accounts:users")
    next_url = _safe_next(request, fallback)
    if not (request.user.can_manage_users() or request.user.can_manage_hr()):
        messages.error(request, "You do not have permission to change roles.")
        return redirect("core:dashboard")
    person = get_object_or_404(User, pk=pk)
    role = request.POST.get("role")
    if role not in User.Role.values:
        messages.error(request, "Unknown role.")
        return redirect(next_url)
    if person == request.user and role != User.Role.ADMIN and request.user.role == User.Role.ADMIN:
        messages.error(request, "You cannot demote your own admin account.")
        return redirect(next_url)
    person.role = role
    update_fields = ["role"]
    if role == User.Role.ADMIN:
        person.is_staff = True
        update_fields.append("is_staff")
    person.save(update_fields=update_fields)
    from accounts.permissions import sync_permissions_from_role

    sync_permissions_from_role(person, reset=True)
    write_audit(request, "user.role_change", object_type="user", object_id=person.pk, detail={"role": role})
    messages.success(request, f"{person.staff_code} is now {person.get_role_display()}.")
    return redirect(next_url)


@login_required
@require_POST
def toggle_permission(request, pk):
    from accounts.permissions import ACTIVITY_CODES, sync_permissions_from_role

    if not request.user.can_manage_hr():
        messages.error(request, "You do not have permission to change employee access.")
        return redirect("core:dashboard")
    person = get_object_or_404(
        User.objects.exclude(role__in=[User.Role.CLIENT, User.Role.PENDING_APPROVAL]),
        pk=pk,
    )
    activity = (request.POST.get("activity") or "").strip()
    if activity not in ACTIVITY_CODES:
        messages.error(request, "Unknown activity.")
        return redirect("accounts:hr-permissions")
    enabled = str(request.POST.get("enabled", "")).strip().lower() in {"1", "true", "on", "yes"}
    sync_permissions_from_role(person)
    perms = person.permissions
    setattr(perms, activity, enabled)
    perms.save(update_fields=[activity, "updated_at"])
    write_audit(
        request,
        "hr.permission.toggle",
        object_type="user",
        object_id=person.pk,
        detail={"activity": activity, "enabled": enabled},
    )
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        from django.http import JsonResponse

        return JsonResponse({"ok": True, "enabled": enabled})
    messages.success(
        request,
        f"{person.staff_code}: {activity.replace('_', ' ')} {'enabled' if enabled else 'disabled'}.",
    )
    return redirect("accounts:hr-permissions")

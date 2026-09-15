from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, ListView, UpdateView

from accounts.forms import EmployeeEditForm, EmployeeRegisterForm, EmployeeSalaryForm, LoginForm
from accounts.mixins import RoleRequiredMixin
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


class HRView(RoleRequiredMixin, ListView):
    template_name = "accounts/hr.html"
    context_object_name = "employees"
    allowed_roles = HR_ROLES
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
    allowed_roles = HR_ROLES
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
    allowed_roles = HR_ROLES
    paginate_by = 25

    def get_queryset(self):
        return User.objects.exclude(role=User.Role.CLIENT).order_by("staff_code")


class HREmployeeEditView(RoleRequiredMixin, UpdateView):
    template_name = "accounts/hr_employee_edit.html"
    form_class = EmployeeEditForm
    context_object_name = "employee"
    allowed_roles = HR_ROLES
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


class HREmployeePermissionsView(RoleRequiredMixin, ListView):
    template_name = "accounts/hr_permissions.html"
    context_object_name = "employees"
    allowed_roles = HR_ROLES
    paginate_by = 25

    def get_queryset(self):
        return (
            User.objects.exclude(role=User.Role.CLIENT)
            .exclude(role=User.Role.PENDING_APPROVAL)
            .order_by("staff_code")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assignable_roles"] = ASSIGNABLE_ROLES
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
    allowed_roles = HR_ROLES
    paginate_by = 25

    def get_queryset(self):
        return _active_staff_qs().select_related("salary")


class HRSalaryRegisterView(RoleRequiredMixin, CreateView):
    template_name = "accounts/hr_salary_form.html"
    form_class = EmployeeSalaryForm
    allowed_roles = HR_ROLES
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
            detail={"staff_code": self.employee.staff_code, "amount": str(self.object.amount)},
        )
        messages.success(self.request, f"Registered salary for {self.employee.staff_code}.")
        return response


class HRSalaryUpdateView(RoleRequiredMixin, UpdateView):
    template_name = "accounts/hr_salary_form.html"
    form_class = EmployeeSalaryForm
    context_object_name = "salary"
    allowed_roles = HR_ROLES
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
            detail={"staff_code": self.employee.staff_code, "amount": str(self.object.amount)},
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
    write_audit(request, "user.role_change", object_type="user", object_id=person.pk, detail={"role": role})
    messages.success(request, f"{person.staff_code} is now {person.get_role_display()}.")
    return redirect(next_url)

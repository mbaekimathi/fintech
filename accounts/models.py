import secrets

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from accounts.fields import MysqlBooleanEnumField, MysqlChoiceEnumField


staff_code_validator = RegexValidator(
    regex=r"^\d{6}$",
    message="Staff code must be exactly 6 digits.",
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, staff_code, password, **extra_fields):
        if not staff_code:
            raise ValueError("A 6-digit staff code is required.")
        staff_code = str(staff_code).zfill(6)
        email = extra_fields.pop("email", "")
        if email:
            email = self.normalize_email(email)
        user = self.model(staff_code=staff_code, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, staff_code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_approved", False)
        extra_fields.setdefault("role", User.Role.PENDING_APPROVAL)
        return self._create_user(staff_code, password, **extra_fields)

    def create_superuser(self, staff_code, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_approved", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("approved_at", timezone.now())
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(staff_code, password, **extra_fields)

    def generate_staff_code(self) -> str:
        for _ in range(50):
            code = f"{secrets.randbelow(900000) + 100000:06d}"
            if not self.filter(staff_code=code).exists():
                return code
        raise RuntimeError("Could not allocate a unique staff code.")


class User(AbstractUser):
    class Role(models.TextChoices):
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        EMPLOYEE = "EMPLOYEE", "Employee"
        CLIENT = "CLIENT", "Client"
        ACCOUNTS = "ACCOUNTS", "Accounts"
        IT_SUPPORT = "IT_SUPPORT", "IT Support"

    username = None
    staff_code = models.CharField(
        "staff code",
        max_length=6,
        unique=True,
        validators=[staff_code_validator],
        help_text="Unique 6-digit login code.",
    )
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=80, blank=True)
    role = MysqlChoiceEnumField(
        max_length=20,
        choices=Role.choices,
        default=Role.PENDING_APPROVAL,
    )
    is_approved = MysqlBooleanEnumField(
        default=False,
        help_text="New employee registrations stay locked until an admin or manager approves them.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approvals_made",
    )
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    approval_password = models.CharField(
        max_length=128,
        blank=True,
        help_text="Hashed 6-digit password used only to approve payment transfers.",
    )

    USERNAME_FIELD = "staff_code"
    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    objects = UserManager()

    class Meta:
        ordering = ["staff_code"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        name = self.get_full_name() or self.email
        return f"{self.staff_code} · {name}"

    @property
    def effective_role(self) -> str:
        """Active role for this request (session switch) or the stored role."""
        return getattr(self, "_effective_role", None) or self.role

    @property
    def is_role_switched(self) -> bool:
        switched = getattr(self, "_effective_role", None)
        return bool(switched) and switched != self.role

    @property
    def role_label(self) -> str:
        return self.Role(self.effective_role).label

    def has_role(self, *roles: str) -> bool:
        return self.effective_role in roles

    @property
    def is_pending(self) -> bool:
        return (not self.is_approved) or self.role == self.Role.PENDING_APPROVAL

    def can_switch_roles(self) -> bool:
        """IT Support may temporarily view the app as another role (session only)."""
        return self.role == self.Role.IT_SUPPORT

    def has_activity(self, code: str) -> bool:
        if self.is_superuser and not self.is_role_switched:
            return True
        from accounts.permissions import activity_enabled, role_default_permissions

        if self.is_role_switched:
            return bool(role_default_permissions(self.effective_role).get(code))
        return activity_enabled(self, code)

    def apply_approval(self, approved: bool, actor=None) -> list[str]:
        """Set approval state and return the fields that changed."""
        self.is_approved = bool(approved)
        update_fields = ["is_approved", "approved_at", "approved_by"]
        if self.is_approved:
            self.approved_at = timezone.now()
            self.approved_by = actor
            if self.role == self.Role.PENDING_APPROVAL:
                self.role = self.Role.EMPLOYEE
                update_fields.append("role")
        else:
            self.approved_at = None
            self.approved_by = None
        return update_fields

    def can_manage_users(self) -> bool:
        return self.has_activity("manage_people")

    def can_manage_hr(self) -> bool:
        return self.has_activity("manage_hr")

    def can_manage_ledger(self) -> bool:
        return self.has_activity("manage_ledger")

    def can_manage_integrations(self) -> bool:
        return self.has_activity("manage_integrations")

    def can_manage_daraja(self) -> bool:
        return self.has_activity("manage_daraja")

    def can_manage_app_settings(self) -> bool:
        return self.has_activity("manage_app_settings")

    def can_review_requests(self) -> bool:
        return self.has_activity("review_requests")

    def can_pin_approval_prompt(self) -> bool:
        return self.has_activity("pin_approval_prompt")

    def can_stk_pin_approval_prompt(self) -> bool:
        return self.has_activity("stk_pin_approval_prompt")

    def requires_app_on_approval(self) -> bool:
        from core.models import AppSettings

        return AppSettings.load().app_approval_required and self.can_pin_approval_prompt()

    def requires_stk_on_approval(self) -> bool:
        from core.models import AppSettings

        return AppSettings.load().stk_pin_approval_required and self.can_stk_pin_approval_prompt()

    def requires_pin_on_approval(self) -> bool:
        return self.requires_app_on_approval() or self.requires_stk_on_approval()

    @property
    def has_approval_password(self) -> bool:
        return bool(self.approval_password)

    def set_approval_password(self, raw_password: str) -> None:
        from django.contrib.auth.hashers import make_password

        self.approval_password = make_password(raw_password)

    def check_approval_password(self, raw_password: str) -> bool:
        from django.contrib.auth.hashers import check_password

        if not self.approval_password:
            return False
        return check_password(raw_password, self.approval_password)

    def can_submit_requests(self) -> bool:
        return self.has_activity("submit_requests")

    def can_view_hub_balance(self) -> bool:
        return self.has_activity("view_hub_balance")


class EmployeePermissions(models.Model):
    """Per-employee workspace activity toggles (seeded from role defaults)."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    submit_requests = MysqlBooleanEnumField(default=False)
    review_requests = MysqlBooleanEnumField(default=False)
    pin_approval_prompt = MysqlBooleanEnumField(default=False)
    stk_pin_approval_prompt = MysqlBooleanEnumField(default=False)
    manage_people = MysqlBooleanEnumField(default=False)
    manage_hr = MysqlBooleanEnumField(default=False)
    manage_ledger = MysqlBooleanEnumField(default=False)
    manage_daraja = MysqlBooleanEnumField(default=False)
    view_hub_balance = MysqlBooleanEnumField(default=False)
    manage_integrations = MysqlBooleanEnumField(default=False)
    manage_app_settings = MysqlBooleanEnumField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "employee permissions"
        verbose_name_plural = "employee permissions"

    def __str__(self):
        return f"Permissions · {self.user.staff_code}"

    def as_flags(self) -> dict[str, bool]:
        return {
            "submit_requests": bool(self.submit_requests),
            "review_requests": bool(self.review_requests),
            "pin_approval_prompt": bool(self.pin_approval_prompt),
            "stk_pin_approval_prompt": bool(self.stk_pin_approval_prompt),
            "manage_people": bool(self.manage_people),
            "manage_hr": bool(self.manage_hr),
            "manage_ledger": bool(self.manage_ledger),
            "manage_daraja": bool(self.manage_daraja),
            "view_hub_balance": bool(self.view_hub_balance),
            "manage_integrations": bool(self.manage_integrations),
            "manage_app_settings": bool(self.manage_app_settings),
        }


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        who = self.actor.staff_code if self.actor else "system"
        return f"{self.created_at:%Y-%m-%d %H:%M} {who} {self.action}"


class EmployeeSalary(models.Model):
    """Monthly salary package and Kenya statutory master data for an employee."""

    class PaymentMethod(models.TextChoices):
        BANK = "BANK", "Bank transfer"
        MPESA = "MPESA", "M-Pesa"
        CASH = "CASH", "Cash"

    employee = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="salary",
    )
    basic_salary = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    house_allowance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    other_allowances = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Gross cash pay (basic + allowances). Kept for list/admin compatibility.
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")

    national_id = models.CharField("national ID / passport", max_length=20, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=11, blank=True)
    nssf_number = models.CharField("NSSF number", max_length=20, blank=True)
    shif_number = models.CharField("SHIF / SHA number", max_length=20, blank=True)

    is_resident = models.BooleanField(default=True)
    is_person_with_disability = models.BooleanField(
        "person with disability (PWD)",
        default=False,
    )
    pwd_exemption_certificate = models.CharField(
        "PWD IT exemption certificate",
        max_length=40,
        blank=True,
    )

    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK,
    )
    bank_name = models.CharField(max_length=80, blank=True)
    bank_branch = models.CharField(max_length=80, blank=True)
    bank_account_number = models.CharField(max_length=34, blank=True)
    mpesa_number = models.CharField("M-Pesa number", max_length=15, blank=True)

    notes = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="salaries_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee__staff_code"]
        verbose_name = "employee salary"
        verbose_name_plural = "employee salaries"

    def __str__(self):
        return f"{self.employee.staff_code} · {self.currency} {self.amount}"

    def compute_gross(self):
        from accounts.kenya_payroll import gross_pay

        return gross_pay(
            self.basic_salary,
            self.house_allowance,
            self.transport_allowance,
            self.other_allowances,
        )

    def statutory_estimate(self):
        from accounts.kenya_payroll import estimate_statutory

        return estimate_statutory(
            basic_salary=self.basic_salary,
            house_allowance=self.house_allowance,
            transport_allowance=self.transport_allowance,
            other_allowances=self.other_allowances,
            is_resident=self.is_resident,
            is_person_with_disability=self.is_person_with_disability,
        )

    def save(self, *args, **kwargs):
        self.amount = self.compute_gross()
        if self.kra_pin:
            self.kra_pin = self.kra_pin.strip().upper()
        if self.currency:
            self.currency = self.currency.strip().upper()
        if self.payment_method == self.PaymentMethod.BANK:
            self.mpesa_number = ""
        elif self.payment_method == self.PaymentMethod.MPESA:
            self.bank_name = ""
            self.bank_branch = ""
            self.bank_account_number = ""
        elif self.payment_method == self.PaymentMethod.CASH:
            self.bank_name = ""
            self.bank_branch = ""
            self.bank_account_number = ""
            self.mpesa_number = ""
        super().save(*args, **kwargs)

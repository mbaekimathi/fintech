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
        if self.is_superuser and not self.is_role_switched:
            return True
        return self.effective_role in {self.Role.ADMIN, self.Role.MANAGER}

    def can_manage_hr(self) -> bool:
        if self.is_superuser and not self.is_role_switched:
            return True
        return self.effective_role in {
            self.Role.ADMIN,
            self.Role.MANAGER,
            self.Role.IT_SUPPORT,
        }

    def can_manage_ledger(self) -> bool:
        if self.is_superuser and not self.is_role_switched:
            return True
        return self.effective_role in {
            self.Role.ADMIN,
            self.Role.MANAGER,
            self.Role.ACCOUNTS,
        }

    def can_manage_integrations(self) -> bool:
        if self.is_superuser and not self.is_role_switched:
            return True
        return self.effective_role in {
            self.Role.ADMIN,
            self.Role.IT_SUPPORT,
        }

    def can_manage_daraja(self) -> bool:
        if self.is_superuser and not self.is_role_switched:
            return True
        return self.effective_role in {
            self.Role.ADMIN,
            self.Role.MANAGER,
            self.Role.IT_SUPPORT,
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
    employee = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="salary",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
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

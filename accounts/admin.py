from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm

from accounts.models import AuditEvent, EmployeeSalary, User

APPROVAL_CHOICES = (
    ("1", "Approved"),
    ("0", "Pending approval"),
)


class UserChangeForm(DjangoUserChangeForm):
    is_approved = forms.ChoiceField(label="Approved", choices=APPROVAL_CHOICES, widget=forms.Select)

    class Meta(DjangoUserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].widget = forms.Select(choices=User.Role.choices)
        if self.instance and self.instance.pk:
            self.initial["is_approved"] = "1" if self.instance.is_approved else "0"

    def clean_is_approved(self):
        return self.cleaned_data["is_approved"] == "1"


class UserCreationForm(DjangoUserCreationForm):
    class Meta(DjangoUserCreationForm.Meta):
        model = User
        fields = ("staff_code", "email", "first_name", "last_name", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].widget = forms.Select(choices=User.Role.choices)


class UserChangelistForm(forms.ModelForm):
    is_approved = forms.ChoiceField(choices=APPROVAL_CHOICES, widget=forms.Select)

    class Meta:
        model = User
        fields = ("role", "is_approved")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].widget = forms.Select(choices=User.Role.choices)
        if self.instance and self.instance.pk:
            self.initial["is_approved"] = "1" if self.instance.is_approved else "0"

    def clean_is_approved(self):
        return self.cleaned_data["is_approved"] == "1"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ("staff_code",)
    list_display = (
        "staff_code",
        "email",
        "first_name",
        "last_name",
        "department",
        "role",
        "is_approved",
        "approved_at",
        "is_active",
    )
    list_display_links = ("staff_code", "email")
    list_editable = ("role", "is_approved")
    list_filter = ("role", "is_approved", "is_active", "is_staff")
    search_fields = ("staff_code", "email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("staff_code", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "email", "phone", "department")}),
        (
            "Access",
            {
                "fields": (
                    "role",
                    "is_approved",
                    "approved_at",
                    "approved_by",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined", "last_login_ip")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("staff_code", "email", "first_name", "last_name", "role", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined", "last_login_ip", "approved_at")

    def get_changelist_form(self, request, **kwargs):
        return UserChangelistForm

    def save_model(self, request, obj, form, change):
        if change and "is_approved" in form.changed_data:
            obj.apply_approval(obj.is_approved, actor=request.user)
        super().save_model(request, obj, form, change)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "ip_address")
    list_filter = ("action",)
    search_fields = ("action", "object_id", "actor__staff_code")
    readonly_fields = (
        "actor",
        "action",
        "object_type",
        "object_id",
        "ip_address",
        "user_agent",
        "detail",
        "created_at",
    )


@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(admin.ModelAdmin):
    list_display = ("employee", "currency", "amount", "updated_by", "updated_at")
    search_fields = ("employee__staff_code", "employee__email", "employee__first_name", "employee__last_name")
    readonly_fields = ("created_at", "updated_at")

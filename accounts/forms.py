from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import User

CODE_WIDGET = forms.TextInput(
    attrs={
        "class": "pin-field",
        "inputmode": "numeric",
        "autocomplete": "username",
        "maxlength": "6",
        "pattern": r"\d{6}",
        "placeholder": "000000",
        "aria-label": "6-digit login code",
    }
)

PIN_WIDGET = forms.PasswordInput(
    attrs={
        "class": "pin-field",
        "inputmode": "numeric",
        "autocomplete": "current-password",
        "maxlength": "6",
        "pattern": r"\d{6}",
        "placeholder": "••••••",
        "aria-label": "6-digit password",
    }
)


class LoginForm(forms.Form):
    staff_code = forms.CharField(label="Login code", min_length=6, max_length=6, widget=CODE_WIDGET)
    password = forms.CharField(label="Password", min_length=6, max_length=6, widget=PIN_WIDGET)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean_staff_code(self):
        code = self.cleaned_data["staff_code"].strip()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError("Enter your 6-digit login code.")
        return code

    def clean(self):
        cleaned = super().clean()
        staff_code = cleaned.get("staff_code")
        password = cleaned.get("password")
        if staff_code and password:
            user = authenticate(self.request, username=staff_code, password=password)
            if user is None:
                raise ValidationError("Invalid login code or password.")
            if not user.is_active:
                raise ValidationError("This account has been deactivated.")
            if user.is_pending:
                raise ValidationError("Your registration is pending approval.")
            self.user_cache = user
        return cleaned

    def get_user(self):
        return self.user_cache


class EmployeeRegisterForm(forms.ModelForm):
    staff_code = forms.CharField(
        label="6-digit login code",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "pin-field",
                "inputmode": "numeric",
                "autocomplete": "username",
                "maxlength": "6",
                "pattern": r"\d{6}",
                "placeholder": "000000",
                "aria-label": "6-digit login code",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password (6 digits)",
        widget=forms.PasswordInput(
            attrs={
                "class": "pin-field",
                "inputmode": "numeric",
                "autocomplete": "new-password",
                "maxlength": "6",
                "pattern": r"\d{6}",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(
            attrs={
                "class": "pin-field",
                "inputmode": "numeric",
                "autocomplete": "new-password",
                "maxlength": "6",
                "pattern": r"\d{6}",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "staff_code")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "field", "autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"class": "field", "autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"class": "field", "autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"class": "field", "autocomplete": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True

    def clean_staff_code(self):
        code = self.cleaned_data["staff_code"].strip()
        if not code.isdigit() or len(code) != 6:
            raise ValidationError("Enter a 6-digit login code.")
        if User.objects.filter(staff_code=code).exists():
            raise ValidationError("That login code is already in use.")
        return code

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"])

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") and cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "The two passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.PENDING_APPROVAL
        user.is_approved = False
        user.is_active = True
        user.department = ""
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import EmployeeSalary, User

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

NEW_PIN_WIDGET = forms.PasswordInput(
    attrs={
        "class": "pin-field",
        "inputmode": "numeric",
        "autocomplete": "new-password",
        "maxlength": "6",
        "pattern": r"\d{6}",
        "placeholder": "••••••",
        "aria-label": "6-digit password",
    }
)

FIELD = forms.TextInput(attrs={"class": "field"})
EMAIL_FIELD = forms.EmailInput(attrs={"class": "field", "autocomplete": "email"})
PHONE_FIELD = forms.TextInput(attrs={"class": "field", "autocomplete": "tel"})


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


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone")
        widgets = {
            "first_name": FIELD,
            "last_name": FIELD,
            "email": EMAIL_FIELD,
            "phone": PHONE_FIELD,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("That email is already in use.")
        return email


class ProfilePasswordForm(forms.Form):
    current_password = forms.CharField(label="Current password", min_length=6, max_length=6, widget=PIN_WIDGET)
    new_password1 = forms.CharField(label="New password", widget=NEW_PIN_WIDGET)
    new_password2 = forms.CharField(label="Confirm new password", widget=NEW_PIN_WIDGET)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data.get("current_password")
        if password and not self.user.check_password(password):
            raise ValidationError("Your current password is incorrect.")
        return password

    def clean_new_password1(self):
        password = self.cleaned_data.get("new_password1")
        if password:
            validate_password(password, self.user)
        return password

    def clean(self):
        cleaned = super().clean()
        new_password1 = cleaned.get("new_password1")
        new_password2 = cleaned.get("new_password2")
        if new_password1 and new_password2 and new_password1 != new_password2:
            self.add_error("new_password2", "The two passwords do not match.")
        return cleaned


class ProfileApprovalPasswordForm(forms.Form):
    old_approval_password = forms.CharField(
        label="Old approval password",
        required=True,
        min_length=6,
        max_length=6,
        widget=PIN_WIDGET,
    )
    new_approval_password1 = forms.CharField(
        label="New approval password",
        min_length=6,
        max_length=6,
        widget=NEW_PIN_WIDGET,
    )
    new_approval_password2 = forms.CharField(
        label="Confirm new approval password",
        min_length=6,
        max_length=6,
        widget=NEW_PIN_WIDGET,
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        self.changing = user.has_approval_password
        super().__init__(*args, **kwargs)
        if self.changing:
            self.fields["old_approval_password"].required = True
            self.fields["new_approval_password1"].label = "New approval password"
            self.fields["new_approval_password2"].label = "Confirm new approval password"
        else:
            del self.fields["old_approval_password"]
            self.fields["new_approval_password1"].label = "Approval password"
            self.fields["new_approval_password2"].label = "Confirm approval password"

    def clean_old_approval_password(self):
        password = (self.cleaned_data.get("old_approval_password") or "").strip()
        if not self.changing:
            return password
        if not password:
            raise ValidationError("Enter your old approval password.")
        if not self.user.check_approval_password(password):
            raise ValidationError("Your old approval password is incorrect.")
        return password

    def _validate_approval_pin(self, password: str, field: str) -> str:
        if not password.isdigit() or len(password) != 6:
            raise ValidationError("Enter a 6-digit approval password.")
        if self.user.check_password(password):
            raise ValidationError("Approval password must be different from your login password.")
        return password

    def clean_new_approval_password1(self):
        password = (self.cleaned_data.get("new_approval_password1") or "").strip()
        return self._validate_approval_pin(password, "new_approval_password1")

    def clean(self):
        cleaned = super().clean()
        new_password1 = cleaned.get("new_approval_password1")
        new_password2 = (cleaned.get("new_approval_password2") or "").strip()
        if new_password2 and new_password2 != new_password1:
            self.add_error("new_approval_password2", "The two approval passwords do not match.")
        return cleaned


class EmployeeEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "department", "is_active")
        widgets = {
            "first_name": FIELD,
            "last_name": FIELD,
            "email": EMAIL_FIELD,
            "phone": PHONE_FIELD,
            "department": FIELD,
            "is_active": forms.CheckboxInput(),
        }
        labels = {
            "is_active": "Active status",
        }
        help_texts = {
            "is_active": "Inactive employees cannot sign in.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("That email is already in use.")
        return email


class EmployeeSalaryForm(forms.ModelForm):
    class Meta:
        model = EmployeeSalary
        fields = (
            "basic_salary",
            "house_allowance",
            "transport_allowance",
            "other_allowances",
            "currency",
            "national_id",
            "kra_pin",
            "nssf_number",
            "shif_number",
            "is_resident",
            "is_person_with_disability",
            "pwd_exemption_certificate",
            "payment_method",
            "bank_name",
            "bank_branch",
            "bank_account_number",
            "mpesa_number",
            "notes",
        )
        widgets = {
            "basic_salary": forms.NumberInput(
                attrs={"class": "field", "step": "0.01", "min": "0", "inputmode": "decimal", "x-model.number": "basic"}
            ),
            "house_allowance": forms.NumberInput(
                attrs={"class": "field", "step": "0.01", "min": "0", "inputmode": "decimal", "x-model.number": "house"}
            ),
            "transport_allowance": forms.NumberInput(
                attrs={
                    "class": "field",
                    "step": "0.01",
                    "min": "0",
                    "inputmode": "decimal",
                    "x-model.number": "transport",
                }
            ),
            "other_allowances": forms.NumberInput(
                attrs={"class": "field", "step": "0.01", "min": "0", "inputmode": "decimal", "x-model.number": "other"}
            ),
            "currency": forms.TextInput(attrs={"class": "field", "maxlength": "3"}),
            "national_id": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
            "kra_pin": forms.TextInput(
                attrs={"class": "field", "maxlength": "11", "placeholder": "A000000000Z", "autocomplete": "off"}
            ),
            "nssf_number": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
            "shif_number": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
            "is_resident": forms.CheckboxInput(attrs={"class": "check", "x-model": "isResident"}),
            "is_person_with_disability": forms.CheckboxInput(attrs={"class": "check", "x-model": "isPwd"}),
            "pwd_exemption_certificate": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
            "payment_method": forms.Select(attrs={"class": "select", "x-model": "paymentMethod"}),
            "bank_name": forms.TextInput(attrs={"class": "field"}),
            "bank_branch": forms.TextInput(attrs={"class": "field"}),
            "bank_account_number": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
            "mpesa_number": forms.TextInput(
                attrs={
                    "class": "field",
                    "inputmode": "tel",
                    "placeholder": "07XXXXXXXX or 2547XXXXXXXX",
                    "autocomplete": "tel",
                }
            ),
            "notes": forms.TextInput(attrs={"class": "field"}),
        }
        labels = {
            "basic_salary": "Basic salary",
            "house_allowance": "House allowance",
            "transport_allowance": "Transport / commuter allowance",
            "other_allowances": "Other cash allowances",
            "currency": "Currency",
            "national_id": "National ID / passport",
            "kra_pin": "KRA PIN",
            "nssf_number": "NSSF number",
            "shif_number": "SHIF / SHA number",
            "is_resident": "Tax resident in Kenya",
            "is_person_with_disability": "Person with disability (PWD tax exemption)",
            "pwd_exemption_certificate": "PWD IT exemption certificate number",
            "payment_method": "Payment method",
            "bank_name": "Bank name",
            "bank_branch": "Bank branch",
            "bank_account_number": "Bank account number",
            "mpesa_number": "M-Pesa number",
            "notes": "Notes",
        }
        help_texts = {
            "basic_salary": "Contractual monthly basic pay before allowances.",
            "house_allowance": "Cash housing allowance paid with salary (not housing benefit in kind).",
            "transport_allowance": "Monthly transport or commuter cash allowance.",
            "other_allowances": "Airtime, leave pay, and other fixed cash allowances.",
            "kra_pin": "11-character PIN required for PAYE / P9 / P10 filing.",
            "nssf_number": "Member number for NSSF remittance returns.",
            "shif_number": "Social Health Authority member number (replaces NHIF).",
            "is_resident": "Residents receive the monthly personal relief of KES 2,400.",
            "is_person_with_disability": "When certified, PAYE is treated as exempt on this estimate.",
            "payment_method": "How this employee should receive net pay each month.",
            "bank_account_number": "Account that should receive net pay.",
            "mpesa_number": "Kenyan mobile number that should receive net pay.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].required = True
        self.fields["basic_salary"].required = True
        self.fields["kra_pin"].required = True
        self.fields["national_id"].required = True
        self.fields["nssf_number"].required = True
        self.fields["shif_number"].required = True
        self.fields["payment_method"].required = True
        for name in (
            "house_allowance",
            "transport_allowance",
            "other_allowances",
            "bank_name",
            "bank_branch",
            "bank_account_number",
            "mpesa_number",
        ):
            self.fields[name].required = False
        if not self.instance.pk and not self.initial.get("currency"):
            self.fields["currency"].initial = "KES"
        if not self.instance.pk and not self.initial.get("payment_method"):
            self.fields["payment_method"].initial = EmployeeSalary.PaymentMethod.BANK
        if self.instance.pk and self.instance.is_person_with_disability:
            self.fields["pwd_exemption_certificate"].required = True

    def clean_currency(self):
        currency = (self.cleaned_data.get("currency") or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValidationError("Enter a 3-letter currency code, e.g. KES.")
        return currency

    def clean_basic_salary(self):
        amount = self.cleaned_data.get("basic_salary")
        if amount is not None and amount <= 0:
            raise ValidationError("Basic salary must be greater than zero.")
        return amount

    def _clean_non_negative(self, field_name: str):
        amount = self.cleaned_data.get(field_name)
        if amount is None:
            return 0
        if amount < 0:
            raise ValidationError("Amount cannot be negative.")
        return amount

    def clean_house_allowance(self):
        return self._clean_non_negative("house_allowance")

    def clean_transport_allowance(self):
        return self._clean_non_negative("transport_allowance")

    def clean_other_allowances(self):
        return self._clean_non_negative("other_allowances")

    def clean_kra_pin(self):
        pin = (self.cleaned_data.get("kra_pin") or "").strip().upper()
        if not pin:
            raise ValidationError("KRA PIN is required for Kenyan payroll filing.")
        if len(pin) != 11 or not pin[0].isalpha() or not pin[-1].isalpha() or not pin[1:-1].isdigit():
            raise ValidationError("Enter a valid KRA PIN, e.g. A123456789Z.")
        return pin

    def clean_national_id(self):
        value = (self.cleaned_data.get("national_id") or "").strip().upper()
        if not value:
            raise ValidationError("National ID or passport number is required.")
        if len(value) < 5:
            raise ValidationError("Enter a valid national ID or passport number.")
        return value

    def clean_nssf_number(self):
        value = (self.cleaned_data.get("nssf_number") or "").strip()
        if not value:
            raise ValidationError("NSSF number is required.")
        if not value.isdigit() or not (7 <= len(value) <= 12):
            raise ValidationError("NSSF numbers are usually 7–12 digits.")
        return value

    def clean_shif_number(self):
        value = (self.cleaned_data.get("shif_number") or "").strip()
        if not value:
            raise ValidationError("SHIF / SHA number is required.")
        if not value.isdigit() or not (6 <= len(value) <= 12):
            raise ValidationError("SHIF / SHA numbers are usually 6–12 digits.")
        return value

    def clean_mpesa_number(self):
        import re

        raw = (self.cleaned_data.get("mpesa_number") or "").strip()
        digits = re.sub(r"\D", "", raw)
        if not digits:
            return ""
        if digits.startswith("254") and len(digits) == 12:
            return digits
        if digits.startswith("0") and len(digits) == 10:
            return "254" + digits[1:]
        if len(digits) == 9:
            return "254" + digits
        raise ValidationError("Enter a Kenyan mobile number such as 07XXXXXXXX or 2547XXXXXXXX.")

    def clean(self):
        cleaned = super().clean()
        is_pwd = cleaned.get("is_person_with_disability")
        cert = (cleaned.get("pwd_exemption_certificate") or "").strip()
        if is_pwd and not cert:
            self.add_error(
                "pwd_exemption_certificate",
                "Enter the PWD IT exemption certificate number when PWD is selected.",
            )
        cleaned["pwd_exemption_certificate"] = cert

        method = cleaned.get("payment_method") or EmployeeSalary.PaymentMethod.BANK
        bank_name = (cleaned.get("bank_name") or "").strip()
        bank_branch = (cleaned.get("bank_branch") or "").strip()
        bank_account = (cleaned.get("bank_account_number") or "").strip()
        mpesa = cleaned.get("mpesa_number") or ""

        if method == EmployeeSalary.PaymentMethod.BANK:
            if not bank_name:
                self.add_error("bank_name", "Enter the bank name for bank transfer.")
            if not bank_account:
                self.add_error("bank_account_number", "Enter the bank account number.")
            cleaned["bank_name"] = bank_name
            cleaned["bank_branch"] = bank_branch
            cleaned["bank_account_number"] = bank_account
            cleaned["mpesa_number"] = ""
        elif method == EmployeeSalary.PaymentMethod.MPESA:
            if not mpesa:
                self.add_error("mpesa_number", "Enter the M-Pesa number for mobile payouts.")
            cleaned["bank_name"] = ""
            cleaned["bank_branch"] = ""
            cleaned["bank_account_number"] = ""
            cleaned["mpesa_number"] = mpesa
        else:
            cleaned["bank_name"] = ""
            cleaned["bank_branch"] = ""
            cleaned["bank_account_number"] = ""
            cleaned["mpesa_number"] = ""
        return cleaned

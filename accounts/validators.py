from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class SixDigitPasswordValidator:
    """Staff passwords are exactly six numeric digits, then hashed by Django."""

    def validate(self, password, user=None):
        if not password or not password.isdigit() or len(password) != 6:
            raise ValidationError(
                _("Password must be exactly 6 digits."),
                code="password_not_six_digits",
            )

    def get_help_text(self):
        return _("Your password must be exactly 6 digits.")

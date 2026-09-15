import re

from django import forms

from paybill.models import MoneyRequest

FIELD = {"class": "field"}
SELECT = {"class": "select"}


class MoneyRequestForm(forms.ModelForm):
    class Meta:
        model = MoneyRequest
        fields = (
            "category",
            "destination_type",
            "destination",
            "account_ref",
            "amount",
            "reason",
        )
        widgets = {
            "category": forms.Select(attrs={**SELECT, "id": "id_money_category"}),
            "destination_type": forms.Select(
                attrs={**SELECT, "id": "id_money_destination_type"}
            ),
            "destination": forms.TextInput(
                attrs={
                    **FIELD,
                    "id": "id_money_destination",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "placeholder": "Phone, paybill, or till",
                }
            ),
            "account_ref": forms.TextInput(
                attrs={
                    **FIELD,
                    "id": "id_money_account_ref",
                    "autocomplete": "off",
                    "placeholder": "Account number on that paybill",
                }
            ),
            "amount": forms.NumberInput(
                attrs={**FIELD, "min": "1", "step": "0.01", "id": "id_money_amount"}
            ),
            "reason": forms.TextInput(
                attrs={
                    **FIELD,
                    "id": "id_money_reason",
                    "placeholder": "Why is this transfer needed?",
                    "maxlength": "255",
                }
            ),
        }
        labels = {
            "category": "Expense category",
            "destination_type": "Transfer to",
            "destination": "Destination details",
            "account_ref": "Account number",
            "amount": "Amount (KES)",
            "reason": "Reason for transfer",
        }
        help_texts = {
            "account_ref": "Required when transferring to a paybill.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].min_value = 1
        self.fields["reason"].required = True

    def clean_destination(self):
        return re.sub(r"\D", "", self.cleaned_data.get("destination") or "")

    def clean_account_ref(self):
        return (self.cleaned_data.get("account_ref") or "").strip()

    def clean_reason(self):
        reason = (self.cleaned_data.get("reason") or "").strip()
        if len(reason) < 5:
            raise forms.ValidationError("Give a short reason (at least 5 characters).")
        return reason

    def clean(self):
        cleaned = super().clean()
        dest_type = cleaned.get("destination_type")
        destination = cleaned.get("destination") or ""
        account_ref = cleaned.get("account_ref") or ""
        if not dest_type or not destination:
            return cleaned

        if dest_type == MoneyRequest.DestinationType.PHONE:
            if not (
                (destination.startswith("254") and len(destination) == 12)
                or (destination.startswith("0") and len(destination) == 10)
                or len(destination) == 9
            ):
                self.add_error(
                    "destination",
                    "Enter a Kenyan mobile number such as 07XXXXXXXX or 2547XXXXXXXX.",
                )
            return cleaned

        if destination.startswith("254") or len(destination) >= 10:
            self.add_error(
                "destination",
                "That looks like a phone number. Choose Phone number, or enter a shortcode / till.",
            )
            return cleaned
        if len(destination) < 5 or len(destination) > 8:
            label = "till" if dest_type == MoneyRequest.DestinationType.TILL else "paybill"
            self.add_error("destination", f"Enter a valid {label} number (5–8 digits).")
            return cleaned
        if dest_type == MoneyRequest.DestinationType.PAYBILL and not account_ref:
            self.add_error("account_ref", "Enter the account number for that paybill.")
        return cleaned

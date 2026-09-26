import re

from django import forms

from paybill.models import CollectionMonitor, MoneyRequest

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


class CollectionMonitorForm(forms.ModelForm):
    class Meta:
        model = CollectionMonitor
        fields = (
            "label",
            "account_type",
            "identifier",
            "account_ref",
            "auto_refresh",
            "use_hub_daraja",
            "daraja_consumer_key",
            "daraja_consumer_secret",
            "daraja_passkey",
            "daraja_shortcode",
        )
        widgets = {
            "label": forms.TextInput(attrs={**FIELD, "placeholder": "e.g. Main shop paybill"}),
            "account_type": forms.Select(attrs=SELECT),
            "identifier": forms.TextInput(
                attrs={
                    **FIELD,
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "placeholder": "Paybill, till, or phone",
                }
            ),
            "account_ref": forms.TextInput(
                attrs={
                    **FIELD,
                    "autocomplete": "off",
                    "placeholder": "Optional paybill account number",
                }
            ),
            "auto_refresh": forms.CheckboxInput(attrs={"class": "check"}),
            "use_hub_daraja": forms.CheckboxInput(attrs={"class": "check"}),
            "daraja_consumer_key": forms.TextInput(attrs={**FIELD, "autocomplete": "off"}),
            "daraja_consumer_secret": forms.PasswordInput(
                attrs={**FIELD, "autocomplete": "new-password"},
                render_value=True,
            ),
            "daraja_passkey": forms.PasswordInput(
                attrs={**FIELD, "autocomplete": "new-password"},
                render_value=True,
            ),
            "daraja_shortcode": forms.TextInput(attrs={**FIELD, "inputmode": "numeric"}),
        }
        labels = {
            "label": "Display name",
            "account_type": "Account type",
            "identifier": "Number",
            "account_ref": "Paybill account no.",
            "auto_refresh": "Auto-refresh live balance",
            "use_hub_daraja": "Use hub Daraja STK credentials",
            "daraja_consumer_key": "Consumer key (override)",
            "daraja_consumer_secret": "Consumer secret (override)",
            "daraja_passkey": "Lipa passkey (override)",
            "daraja_shortcode": "Lipa shortcode (override)",
        }
        help_texts = {
            "account_ref": "Optional. Extra paybill account label; collections use the unique collection code.",
            "auto_refresh": "Poll Safaricom when balance API is configured (same initiator as hub).",
            "use_hub_daraja": "When checked, STK uses hub Daraja setup but still tags payments with this account's collection code.",
            "daraja_shortcode": "Required when overriding credentials — the shortcode registered on your Daraja app.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("daraja_consumer_secret", "daraja_passkey"):
            self.fields[name].required = False

    def clean_identifier(self):
        from paybill.automation import normalize_monitor_identifier

        account_type = self.cleaned_data.get("account_type") or self.data.get("account_type")
        raw = self.cleaned_data.get("identifier") or ""
        if not account_type:
            return raw
        try:
            return normalize_monitor_identifier(account_type, raw)
        except Exception as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_account_ref(self):
        return (self.cleaned_data.get("account_ref") or "").strip()

    def clean(self):
        cleaned = super().clean()
        account_type = cleaned.get("account_type")
        identifier = cleaned.get("identifier") or ""
        if not account_type or not identifier:
            return cleaned
        if account_type in (
            CollectionMonitor.AccountType.PAYBILL,
            CollectionMonitor.AccountType.TILL,
        ):
            if identifier.startswith("254") or len(identifier) >= 10:
                self.add_error(
                    "identifier",
                    "That looks like a phone number. Choose Phone number or enter a paybill/till.",
                )
            elif len(identifier) < 5 or len(identifier) > 8:
                label = "till" if account_type == CollectionMonitor.AccountType.TILL else "paybill"
                self.add_error("identifier", f"Enter a valid {label} number (5–8 digits).")
        elif account_type == CollectionMonitor.AccountType.PHONE:
            cleaned["account_ref"] = ""
        return cleaned


class CollectionMonitorPayoutForm(forms.ModelForm):
    class Meta:
        model = CollectionMonitor
        fields = ("auto_payout_enabled", "auto_payout_phone")
        widgets = {
            "auto_payout_enabled": forms.CheckboxInput(attrs={"class": "check"}),
            "auto_payout_phone": forms.TextInput(
                attrs={
                    **FIELD,
                    "inputmode": "tel",
                    "autocomplete": "tel",
                    "placeholder": "07XX XXX XXX or 2547…",
                }
            ),
        }
        labels = {
            "auto_payout_enabled": "Auto-send to client",
            "auto_payout_phone": "Client phone",
        }
        help_texts = {
            "auto_payout_enabled": "After each inbound collection, queue a B2C payout to the client phone.",
            "auto_payout_phone": "Kenyan mobile number that receives the collected amount.",
        }

    def clean_auto_payout_phone(self):
        from paybill.auto_payout import normalize_client_phone

        raw = (self.cleaned_data.get("auto_payout_phone") or "").strip()
        enabled = self.cleaned_data.get("auto_payout_enabled")
        if not enabled:
            return raw
        if not raw:
            raise forms.ValidationError("Enter the client phone when auto-send is enabled.")
        try:
            return normalize_client_phone(raw)
        except Exception as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("auto_payout_enabled") and not (cleaned.get("auto_payout_phone") or "").strip():
            self.add_error("auto_payout_phone", "Enter the client phone when auto-send is enabled.")
        return cleaned

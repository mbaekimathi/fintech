from django import forms

from integrations.daraja import apply_sandbox_to_instance
from integrations.models import DarajaConfig
from paybill.models import PaybillAccount

SECRET_FIELDS = ("consumer_secret", "passkey", "security_credential")

FIELD_WIDGETS = {
    "environment": forms.Select(attrs={"class": "select", "id": "id_environment"}),
    "consumer_key": forms.TextInput(
        attrs={
            "class": "field",
            "autocomplete": "off",
            "placeholder": "Paste from your Daraja app",
        }
    ),
    "consumer_secret": forms.TextInput(
        attrs={
            "class": "field secret-box",
            "autocomplete": "off",
            "spellcheck": "false",
            "placeholder": "Paste from your Daraja app",
        }
    ),
    "shortcode": forms.TextInput(attrs={"class": "field", "inputmode": "numeric"}),
    "org_shortcode": forms.TextInput(attrs={"class": "field", "inputmode": "numeric"}),
    "till_number": forms.TextInput(attrs={"class": "field", "inputmode": "numeric"}),
    "paybill_account": forms.Select(attrs={"class": "select"}),
    "passkey": forms.TextInput(
        attrs={"class": "field secret-box", "autocomplete": "off", "spellcheck": "false"}
    ),
    "stk_callback_url": forms.URLInput(
        attrs={"class": "field", "placeholder": "https://your-host/api/v1/daraja/stk/callback/"}
    ),
    "stk_transaction_type": forms.Select(attrs={"class": "select"}),
    "stk_account_reference": forms.TextInput(attrs={"class": "field", "placeholder": "Invoice, order, or account no."}),
    "stk_transaction_desc": forms.TextInput(attrs={"class": "field", "placeholder": "Payment"}),
    "initiator_name": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
    "security_credential": forms.TextInput(
        attrs={"class": "field secret-box", "autocomplete": "off", "spellcheck": "false"}
    ),
    "result_url": forms.URLInput(attrs={"class": "field", "placeholder": "https://your-host/api/v1/daraja/result/"}),
    "timeout_url": forms.URLInput(attrs={"class": "field", "placeholder": "https://your-host/api/v1/daraja/timeout/"}),
    "balance_identifier_type": forms.Select(attrs={"class": "select"}),
    "balance_remarks": forms.TextInput(attrs={"class": "field", "placeholder": "Balance"}),
    "b2c_enabled": forms.CheckboxInput(attrs={"class": "check"}),
    "b2c_command_id": forms.Select(attrs={"class": "select"}),
    "b2c_remarks": forms.TextInput(attrs={"class": "field", "placeholder": "Payout"}),
    "b2c_occasion": forms.TextInput(attrs={"class": "field", "placeholder": "Payment"}),
    "b2b_enabled": forms.CheckboxInput(attrs={"class": "check"}),
    "b2b_sender_identifier_type": forms.Select(attrs={"class": "select"}),
    "b2b_paybill_command": forms.Select(attrs={"class": "select"}),
    "b2b_till_command": forms.Select(attrs={"class": "select"}),
    "b2b_remarks": forms.TextInput(attrs={"class": "field", "placeholder": "Transfer"}),
}


class DarajaSetupForm(forms.ModelForm):
    class Meta:
        model = DarajaConfig
        fields = (
            "environment",
            "paybill_account",
            "shortcode",
            "org_shortcode",
            "till_number",
            "consumer_key",
            "consumer_secret",
            "passkey",
            "stk_transaction_type",
            "stk_account_reference",
            "stk_transaction_desc",
            "stk_callback_url",
            "initiator_name",
            "security_credential",
            "result_url",
            "timeout_url",
            "balance_identifier_type",
            "balance_remarks",
            "b2c_enabled",
            "b2c_command_id",
            "b2c_remarks",
            "b2c_occasion",
            "b2b_enabled",
            "b2b_sender_identifier_type",
            "b2b_paybill_command",
            "b2b_till_command",
            "b2b_remarks",
        )
        widgets = FIELD_WIDGETS
        labels = {
            "environment": "Daraja environment",
            "paybill_account": "Hub paybill",
            "shortcode": "STK paybill shortcode",
            "org_shortcode": "Organization shortcode",
            "till_number": "Till number",
            "consumer_key": "Consumer key",
            "consumer_secret": "Consumer secret",
            "passkey": "Lipa Na M-Pesa passkey",
            "stk_transaction_type": "STK transaction type",
            "stk_account_reference": "Default account reference",
            "stk_transaction_desc": "STK description",
            "stk_callback_url": "STK callback URL",
            "initiator_name": "Initiator username",
            "security_credential": "Security credential",
            "result_url": "Result URL",
            "timeout_url": "Timeout URL",
            "balance_identifier_type": "Balance identifier type",
            "balance_remarks": "Balance remarks",
            "b2c_enabled": "Enable send to phone (B2C)",
            "b2c_command_id": "B2C command",
            "b2c_remarks": "B2C remarks",
            "b2c_occasion": "B2C occasion",
            "b2b_enabled": "Enable send to paybill or till (B2B)",
            "b2b_sender_identifier_type": "B2B sender identifier",
            "b2b_paybill_command": "Command when sending to a paybill",
            "b2b_till_command": "Command when sending to a till",
            "b2b_remarks": "B2B remarks",
        }
        help_texts = {
            "environment": "Sandbox auto-fills Safaricom test shortcode, passkey, initiator, and callback paths.",
            "paybill_account": "The NEXUS paybill STK receipts should post into.",
            "shortcode": "Sandbox STK uses 174379. Production uses your live Lipa Na M-Pesa shortcode.",
            "org_shortcode": "From Daraja → Test credentials → Shortcode 1. Not the STK till 174379.",
            "till_number": "Needed for Buy Goods STK or till payouts when the till is not the same as the shortcode.",
            "consumer_key": "From your Daraja app at developer.safaricom.co.ke. Unique to you — not auto-filled.",
            "consumer_secret": "From the same Daraja app. Leave blank to keep the secret already saved.",
            "passkey": "Sandbox uses Safaricom’s published test passkey. Production uses your live Lipa Na M-Pesa passkey.",
            "stk_transaction_type": "CustomerPayBillOnline collects into a paybill. CustomerBuyGoodsOnline collects into a till.",
            "stk_account_reference": "Shown on the customer’s STK prompt and stored against the ledger posting.",
            "stk_transaction_desc": "Short description sent with the STK prompt (max 13 characters is safest).",
            "stk_callback_url": "HTTPS URL Safaricom calls after the customer enters PIN. On localhost, swap the host for an ngrok HTTPS URL and keep the path.",
            "initiator_name": "Initiator Name (Shortcode 1) on the Daraja Test credentials page. Use the value your portal shows.",
            "security_credential": "Initiator password from that same page. Paste plaintext — NEXUS encrypts it when calling Safaricom.",
            "result_url": "HTTPS URL Safaricom posts balance and payout results to.",
            "timeout_url": "HTTPS URL Safaricom posts if the request times out.",
            "balance_identifier_type": "Use paybill/organization shortcode (4) for a paybill float. Use till (2) for a till.",
            "balance_remarks": "Sent with the Account Balance query.",
            "b2c_enabled": "Turn on Daraja B2C so this shortcode can send to a phone number.",
            "b2c_command_id": "BusinessPayment for general payouts. SalaryPayment or PromotionPayment if that is how the shortcode is configured.",
            "b2c_remarks": "Sent with each B2C payout.",
            "b2c_occasion": "Optional occasion string on the B2C request.",
            "b2b_enabled": "Turn on Daraja B2B so this shortcode can send to another paybill or till.",
            "b2b_sender_identifier_type": "Almost always paybill/organization shortcode (4) — this is your source account.",
            "b2b_paybill_command": "BusinessPayBill when the destination is another paybill.",
            "b2b_till_command": "BusinessBuyGoods when the destination is a till.",
            "b2b_remarks": "Sent with each B2B transfer.",
        }

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        self.fields["paybill_account"].queryset = PaybillAccount.objects.filter(is_active=True)
        self.fields["paybill_account"].required = False
        self.fields["paybill_account"].empty_label = "Select a paybill account"
        for name in SECRET_FIELDS:
            self.fields[name].required = False
        for name in (
            "till_number",
            "stk_account_reference",
            "stk_transaction_desc",
            "balance_remarks",
            "b2c_remarks",
            "b2c_occasion",
            "b2b_remarks",
        ):
            self.fields[name].required = False
        self.fields["b2c_enabled"].required = False
        self.fields["b2b_enabled"].required = False

    def clean_shortcode(self):
        return (self.cleaned_data.get("shortcode") or "").strip()

    def clean_till_number(self):
        return (self.cleaned_data.get("till_number") or "").strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.instance.pk:
            stored = DarajaConfig.objects.filter(pk=self.instance.pk).first()
            if stored:
                for field in SECRET_FIELDS:
                    if not (self.cleaned_data.get(field) or "").strip():
                        setattr(instance, field, getattr(stored, field))
        if instance.environment == DarajaConfig.Environment.SANDBOX:
            apply_sandbox_to_instance(instance, self.request, force=True)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


FIELD = {"class": "field"}
SELECT = {"class": "select"}


class StkPromptForm(forms.Form):
    phone = forms.CharField(
        label="Phone number",
        max_length=15,
        widget=forms.TextInput(attrs={**FIELD, "inputmode": "tel", "placeholder": "254708374149"}),
    )
    amount = forms.DecimalField(
        label="Amount (KES)",
        min_value=1,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={**FIELD, "min": "1", "step": "1"}),
    )
    account_ref = forms.CharField(
        label="Account reference",
        max_length=12,
        required=False,
        widget=forms.TextInput(attrs={**FIELD, "placeholder": "Invoice or account no."}),
    )


class BalanceQueryForm(forms.Form):
    identifier = forms.ChoiceField(
        label="Query",
        choices=(
            ("4", "Paybill / organization shortcode"),
            ("2", "Till number"),
        ),
        widget=forms.Select(attrs=SELECT),
    )


class SendMoneyForm(forms.Form):
    destination_type = forms.ChoiceField(
        label="Send to",
        choices=(
            ("PHONE", "Phone number"),
            ("PAYBILL", "Another paybill"),
            ("TILL", "Till / Buy Goods"),
        ),
        widget=forms.Select(attrs=SELECT),
    )
    destination = forms.CharField(
        label="Destination",
        max_length=20,
        widget=forms.TextInput(attrs={**FIELD, "placeholder": "254708374149 or 600000"}),
    )
    amount = forms.DecimalField(
        label="Amount (KES)",
        min_value=1,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={**FIELD, "min": "1", "step": "1"}),
    )
    account_ref = forms.CharField(
        label="Account number",
        max_length=12,
        required=False,
        widget=forms.TextInput(attrs={**FIELD, "placeholder": "Required for paybill"}),
    )

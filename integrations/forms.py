import re

from django import forms

from integrations.daraja import (
    SANDBOX_ACCOUNT_REF,
    SANDBOX_BALANCE_REMARKS,
    SANDBOX_B2B_REMARKS,
    SANDBOX_B2C_OCCASION,
    SANDBOX_B2C_REMARKS,
    SANDBOX_STK_DESC,
    apply_sandbox_to_instance,
    form_callback_urls,
)
from integrations.models import DarajaConfig
from paybill.models import PaybillAccount

SECRET_FIELDS = (
    "consumer_secret",
    "passkey",
    "security_credential",
    "agent_consumer_secret",
    "agent_security_credential",
)

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
    "agent_shop_enabled": forms.CheckboxInput(attrs={"class": "check"}),
    "agent_channel": forms.Select(attrs={"class": "select", "id": "id_agent_channel"}),
    "agent_till_number": forms.TextInput(attrs={"class": "field", "inputmode": "numeric", "placeholder": "Agent till"}),
    "agent_head_office": forms.TextInput(attrs={"class": "field", "inputmode": "numeric", "placeholder": "Head office shortcode"}),
    "agent_store_number": forms.TextInput(attrs={"class": "field", "placeholder": "Store / outlet ref"}),
    "agent_operator_id": forms.TextInput(attrs={"class": "field", "placeholder": "Operator id"}),
    "agent_api_enabled": forms.CheckboxInput(attrs={"class": "check"}),
    "agent_use_shared_app": forms.CheckboxInput(attrs={"class": "check"}),
    "agent_consumer_key": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
    "agent_consumer_secret": forms.TextInput(
        attrs={"class": "field secret-box", "autocomplete": "off", "spellcheck": "false"}
    ),
    "agent_initiator_name": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
    "agent_security_credential": forms.TextInput(
        attrs={"class": "field secret-box", "autocomplete": "off", "spellcheck": "false"}
    ),
    "agent_api_base_url": forms.URLInput(
        attrs={"class": "field", "placeholder": "https://api.safaricom.co.ke"}
    ),
    "agent_deposit_path": forms.TextInput(
        attrs={"class": "field", "placeholder": "/mpesa/agent/v1/deposit"}
    ),
    "agent_withdraw_path": forms.TextInput(
        attrs={"class": "field", "placeholder": "/mpesa/agent/v1/withdraw"}
    ),
    "agent_deposit_command": forms.TextInput(attrs={"class": "field", "placeholder": "Deposit command / product code"}),
    "agent_withdraw_command": forms.TextInput(attrs={"class": "field", "placeholder": "Withdraw command / product code"}),
    "agent_deposit_callback_url": forms.URLInput(attrs={"class": "field"}),
    "agent_withdraw_callback_url": forms.URLInput(attrs={"class": "field"}),
    "agent_result_url": forms.URLInput(attrs={"class": "field"}),
    "agent_timeout_url": forms.URLInput(attrs={"class": "field"}),
    "agent_track_commission": forms.CheckboxInput(attrs={"class": "check"}),
    "agent_api_notes": forms.Textarea(attrs={"class": "field", "rows": 4, "placeholder": "Paste Safaricom API pack notes here"}),
    "agent_cash_in_enabled": forms.CheckboxInput(attrs={"class": "check"}),
    "agent_cash_out_enabled": forms.CheckboxInput(attrs={"class": "check"}),
    "agent_min_amount": forms.NumberInput(attrs={"class": "field", "min": "1", "step": "1"}),
    "agent_max_amount": forms.NumberInput(attrs={"class": "field", "min": "1", "step": "1"}),
    "agent_daily_limit": forms.NumberInput(attrs={"class": "field", "min": "0", "step": "1"}),
    "agent_cash_in_fee": forms.NumberInput(attrs={"class": "field", "min": "0", "step": "1"}),
    "agent_cash_out_fee": forms.NumberInput(attrs={"class": "field", "min": "0", "step": "1"}),
    "agent_cash_in_account_ref": forms.TextInput(
        attrs={"class": "field", "placeholder": "AGENT", "autocomplete": "off"}
    ),
    "agent_float_warn_kes": forms.NumberInput(attrs={"class": "field", "min": "0", "step": "1"}),
    "agent_receipt_prefix": forms.TextInput(
        attrs={"class": "field", "placeholder": "AG", "autocomplete": "off"}
    ),
}

DARAJA_LABELS = {
    "environment": "Daraja environment",
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
    "b2b_enabled": "Enable paybill and till payouts",
    "b2b_sender_identifier_type": "Float source type",
    "b2b_paybill_command": "Command when paying a paybill",
    "b2b_till_command": "Command when paying a till",
    "b2b_remarks": "Remarks on each transfer",
    "agent_shop_enabled": "Enable agent shop logic",
    "agent_channel": "Agent channel",
    "agent_till_number": "Agent till number",
    "agent_head_office": "Head office shortcode",
    "agent_store_number": "Store / outlet number",
    "agent_operator_id": "Operator id",
    "agent_api_enabled": "Enable official agent APIs (when issued)",
    "agent_use_shared_app": "Reuse shared Daraja app credentials",
    "agent_consumer_key": "Agent consumer key",
    "agent_consumer_secret": "Agent consumer secret",
    "agent_initiator_name": "Agent initiator username",
    "agent_security_credential": "Agent security credential",
    "agent_api_base_url": "Agent API base URL",
    "agent_deposit_path": "Deposit API path",
    "agent_withdraw_path": "Withdraw API path",
    "agent_deposit_command": "Deposit command / product code",
    "agent_withdraw_command": "Withdraw command / product code",
    "agent_deposit_callback_url": "Deposit callback URL",
    "agent_withdraw_callback_url": "Withdraw callback URL",
    "agent_result_url": "Agent result URL",
    "agent_timeout_url": "Agent timeout URL",
    "agent_track_commission": "Track Safaricom agent commission",
    "agent_api_notes": "Safaricom API pack notes",
    "agent_cash_in_enabled": "Allow deposit (cash-in) for a phone",
    "agent_cash_out_enabled": "Allow withdraw (cash-out) for a phone",
    "agent_min_amount": "Minimum amount (KES)",
    "agent_max_amount": "Maximum amount (KES)",
    "agent_daily_limit": "Daily limit per agent (KES)",
    "agent_cash_in_fee": "Your cash-in fee (KES)",
    "agent_cash_out_fee": "Your cash-out fee (KES)",
    "agent_cash_in_account_ref": "Cash-in account reference",
    "agent_float_warn_kes": "Low-float warning (KES)",
    "agent_receipt_prefix": "Receipt prefix",
}

DARAJA_HELP = {
    "environment": "Sandbox uses Safaricom test values. Production is your live key, secret, passkey, and number.",
    "shortcode": "Usually the same as your paybill. Sandbox STK uses 174379.",
    "org_shortcode": "Party A for balance and payouts. Production is often the same paybill. Sandbox Shortcode 1 is 600996.",
    "till_number": "Needed for Buy Goods STK or till payouts when the till is not the same as the shortcode.",
    "consumer_key": "From your Daraja app at developer.safaricom.co.ke. Use the production app for live money.",
    "consumer_secret": "From the same Daraja app. Leave blank to keep the secret already saved.",
    "passkey": "Sandbox uses Safaricom’s published test passkey. Production uses your live Lipa Na M-Pesa passkey.",
    "stk_transaction_type": "CustomerPayBillOnline collects into a paybill. CustomerBuyGoodsOnline collects into a till.",
    "stk_account_reference": "Shown on the customer’s STK prompt and stored against the ledger posting.",
    "stk_transaction_desc": "Short description sent with the STK prompt (max 13 characters is safest).",
    "stk_callback_url": "HTTPS URL Safaricom calls after the customer enters PIN. Fills from https://fin.richcom.co.ke automatically.",
    "initiator_name": "Initiator username from Daraja. Production uses your live initiator, not testapi.",
    "security_credential": "Initiator password. Paste plaintext — NEXUS encrypts it when calling Safaricom.",
    "result_url": "HTTPS URL Safaricom posts balance and payout results to.",
    "timeout_url": "HTTPS URL Safaricom posts if the request times out.",
    "balance_identifier_type": "Use paybill/organization shortcode (4) for a paybill float. Use till (2) for a till.",
    "balance_remarks": "Sent with the Account Balance query.",
    "b2c_enabled": "Turn on Daraja B2C so this shortcode can send to a phone number.",
    "b2c_command_id": "BusinessPayment for general payouts. SalaryPayment or PromotionPayment if that is how the shortcode is configured.",
    "b2c_remarks": "Sent with each B2C payout.",
    "b2c_occasion": "Optional occasion string on the B2C request.",
    "b2b_enabled": "Allows money requests and the test page to pay a paybill or Buy Goods till.",
    "b2b_sender_identifier_type": "Leave as paybill/organization shortcode unless your float sits on a till.",
    "b2b_paybill_command": "Leave as BusinessPayBill unless Safaricom told you otherwise.",
    "b2b_till_command": "Leave as BusinessBuyGoods unless Safaricom told you otherwise.",
    "b2b_remarks": "Shown on the M-Pesa statement for each transfer.",
    "agent_shop_enabled": "Turn on deposit and withdraw for customer phones from this hub.",
    "agent_channel": "Business shop uses STK + B2C today. Official Safaricom agent is for after you register and receive API access.",
    "agent_till_number": "Till / outlet number from your M-Pesa agent registration.",
    "agent_head_office": "Head-office shortcode from your dealer agreement, if any.",
    "agent_store_number": "Optional store reference for multi-outlet agents.",
    "agent_operator_id": "Optional operator id from the Safaricom pack.",
    "agent_api_enabled": "Only turn on when Safaricom has issued agent deposit/withdraw API access.",
    "agent_use_shared_app": "On = use Daraja app credentials. Off = paste a separate agent app key/secret.",
    "agent_consumer_key": "Only needed when not reusing the shared Daraja app.",
    "agent_consumer_secret": "Leave blank to keep the secret already saved.",
    "agent_initiator_name": "Optional separate initiator for agent APIs. Leave blank to reuse balance initiator later.",
    "agent_security_credential": "Initiator password for the agent app. Leave blank to keep saved value.",
    "agent_api_base_url": "Host from Safaricom docs. Blank uses the shared Daraja environment host.",
    "agent_deposit_path": "Paste from the Safaricom API pack when you have it.",
    "agent_withdraw_path": "Paste from the Safaricom API pack when you have it.",
    "agent_deposit_command": "CommandID / product code for deposit, when provided.",
    "agent_withdraw_command": "CommandID / product code for withdraw, when provided.",
    "agent_deposit_callback_url": "HTTPS URL Safaricom will call after a deposit.",
    "agent_withdraw_callback_url": "HTTPS URL Safaricom will call after a withdraw.",
    "agent_result_url": "HTTPS URL for async agent results.",
    "agent_timeout_url": "HTTPS URL if an agent request times out.",
    "agent_track_commission": "When Safaricom pays agent commission, keep it on the ledger when the payload includes it.",
    "agent_api_notes": "Free-form notes from registration / API onboarding.",
    "agent_cash_in_enabled": "Business channel uses STK. Safaricom channel uses agent deposit when APIs are wired.",
    "agent_cash_out_enabled": "Business channel uses B2C. Safaricom channel uses agent withdraw when APIs are wired.",
    "agent_min_amount": "Reject agent transactions below this amount.",
    "agent_max_amount": "Reject agent transactions above this amount.",
    "agent_daily_limit": "0 means no extra daily cap beyond Safaricom limits.",
    "agent_cash_in_fee": "Your shop fee on business channel only — not Safaricom agent commission.",
    "agent_cash_out_fee": "Your shop fee on business channel only — not Safaricom agent commission.",
    "agent_cash_in_account_ref": "Default AccountReference on cash-in (max 12 chars is safest).",
    "agent_float_warn_kes": "Surface a warning when float is below this.",
    "agent_receipt_prefix": "Used when generating agent receipt references.",
}


class _DarajaFormBase(forms.ModelForm):
    """Shared save helpers for Daraja section forms."""

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        for name in self.fields:
            self.fields[name].required = False
        for name in SECRET_FIELDS:
            if name in self.fields:
                self.fields[name].required = False
        urls = form_callback_urls(self.request)
        for name, value in urls.items():
            if name not in self.fields:
                continue
            self.fields[name].widget.attrs["placeholder"] = value
            if not self.is_bound:
                current = str(self.fields[name].initial or getattr(self.instance, name, "") or "")
                if not current or "localhost" in current or "127.0.0.1" in current or "ngrok" in current:
                    self.fields[name].initial = value

    def _keep_secrets(self, instance):
        if not self.instance.pk:
            return
        stored = DarajaConfig.objects.filter(pk=self.instance.pk).first()
        if not stored:
            return
        for field in SECRET_FIELDS:
            if field in self.fields and not (self.cleaned_data.get(field) or "").strip():
                setattr(instance, field, getattr(stored, field))

    def _fill_empty(self, instance, **values):
        for name, value in values.items():
            if value and not str(getattr(instance, name, "") or "").strip():
                setattr(instance, name, value)

    def _apply_callback_urls(self, instance, *names):
        urls = form_callback_urls(self.request)
        for name in names:
            value = urls.get(name)
            if value:
                setattr(instance, name, value)


class DarajaSetupForm(_DarajaFormBase):
    CHANNEL_PAYBILL = "PAYBILL"
    CHANNEL_TILL = "TILL"
    CHANNEL_CHOICES = (
        (CHANNEL_PAYBILL, "Paybill — collect and disburse from a paybill"),
        (CHANNEL_TILL, "Till — collect and disburse from a Buy Goods till"),
    )

    channel = forms.ChoiceField(
        label="Collect and disburse with",
        choices=CHANNEL_CHOICES,
        initial=CHANNEL_PAYBILL,
        widget=forms.Select(attrs={"class": "select", "id": "id_channel"}),
        help_text="Paybill uses Lipa Na M-Pesa Online (CustomerPayBillOnline). Till uses Buy Goods (CustomerBuyGoodsOnline).",
    )
    hub_paybill = forms.CharField(
        label="Paybill or till number",
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "field",
                "inputmode": "numeric",
                "placeholder": "Type the paybill or till number",
                "autocomplete": "off",
                "id": "id_hub_paybill",
            }
        ),
        help_text="Your live number. Shortcode and callback URLs fill from this. Sandbox uses 174379.",
    )

    class Meta:
        model = DarajaConfig
        fields = (
            "environment",
            "shortcode",
            "org_shortcode",
            "till_number",
            "consumer_key",
            "consumer_secret",
        )
        widgets = FIELD_WIDGETS
        labels = DARAJA_LABELS
        help_texts = DARAJA_HELP

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, request=request, **kwargs)
        channel = self.CHANNEL_TILL if self._instance_is_till() else self.CHANNEL_PAYBILL
        if self.is_bound:
            channel = (self.data.get("channel") or channel).strip() or channel
        self.fields["channel"].initial = channel
        self.fields["channel"].required = False
        account = getattr(self.instance, "paybill_account", None)
        stored_number = (account.paybill_number if account else "") or (
            (self.instance.till_number if channel == self.CHANNEL_TILL else "")
            or getattr(self.instance, "shortcode", "")
            or ""
        )
        self.fields["hub_paybill"].initial = stored_number
        till = channel == self.CHANNEL_TILL
        self.fields["hub_paybill"].label = "Till number" if till else "Paybill number"
        self.fields["hub_paybill"].widget.attrs["placeholder"] = (
            "Your live till, e.g. 123456" if till else "Your live paybill, e.g. 888555"
        )

    def _instance_is_till(self) -> bool:
        return str(getattr(self.instance, "stk_transaction_type", "") or "") == DarajaConfig.StkTransactionType.BUY_GOODS

    def clean_hub_paybill(self):
        digits = re.sub(r"\D", "", self.cleaned_data.get("hub_paybill") or "")
        if digits and len(digits) < 5:
            raise forms.ValidationError("Enter a valid paybill or till number.")
        return digits

    def clean_shortcode(self):
        return (self.cleaned_data.get("shortcode") or "").strip()

    def clean_org_shortcode(self):
        return (self.cleaned_data.get("org_shortcode") or "").strip()

    def clean_till_number(self):
        return (self.cleaned_data.get("till_number") or "").strip()

    def _ensure_store(self, number: str, *, till: bool) -> PaybillAccount:
        account = PaybillAccount.objects.filter(paybill_number=number).order_by("id").first()
        kind = "till" if till else "paybill"
        if account:
            if not account.is_active:
                account.is_active = True
                account.save(update_fields=["is_active"])
            return account
        return PaybillAccount.objects.create(
            paybill_number=number,
            account_name=f"M-Pesa {kind} {number}",
            provider=PaybillAccount.Provider.MPESA,
            is_active=True,
            short_code_notes=f"Entered on Daraja setup as {kind}",
        )

    def _apply_channel(self, instance, channel: str, number: str):
        till = channel == self.CHANNEL_TILL
        instance.stk_transaction_type = (
            DarajaConfig.StkTransactionType.BUY_GOODS if till else DarajaConfig.StkTransactionType.PAYBILL
        )
        instance.balance_identifier_type = (
            DarajaConfig.IdentifierType.TILL if till else DarajaConfig.IdentifierType.SHORTCODE
        )
        instance.b2b_sender_identifier_type = (
            DarajaConfig.IdentifierType.TILL if till else DarajaConfig.IdentifierType.SHORTCODE
        )
        if not number:
            return
        instance.paybill_account = self._ensure_store(number, till=till)
        instance.shortcode = number
        instance.org_shortcode = number
        instance.till_number = number if till else (instance.till_number or "")

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._keep_secrets(instance)
        channel = self.cleaned_data.get("channel") or self.CHANNEL_PAYBILL
        number = (self.cleaned_data.get("hub_paybill") or instance.shortcode or instance.till_number or "").strip()
        if instance.environment == DarajaConfig.Environment.SANDBOX:
            apply_sandbox_to_instance(instance, self.request, force=True)
            if channel == self.CHANNEL_TILL:
                instance.stk_transaction_type = DarajaConfig.StkTransactionType.BUY_GOODS
                instance.till_number = instance.till_number or instance.shortcode or "174379"
                instance.balance_identifier_type = DarajaConfig.IdentifierType.TILL
                instance.b2b_sender_identifier_type = DarajaConfig.IdentifierType.TILL
        else:
            self._apply_channel(instance, channel, number)
        self._fill_empty(
            instance,
            stk_account_reference=SANDBOX_ACCOUNT_REF,
            stk_transaction_desc=SANDBOX_STK_DESC,
            balance_remarks=SANDBOX_BALANCE_REMARKS,
            b2c_remarks=SANDBOX_B2C_REMARKS,
            b2c_occasion=SANDBOX_B2C_OCCASION,
            b2b_remarks=SANDBOX_B2B_REMARKS,
            agent_cash_in_account_ref="AGENT",
            agent_receipt_prefix="AG",
        )
        self._apply_callback_urls(instance, "stk_callback_url", "result_url", "timeout_url")
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DarajaStkForm(_DarajaFormBase):
    class Meta:
        model = DarajaConfig
        fields = (
            "stk_transaction_type",
            "passkey",
            "stk_account_reference",
            "stk_transaction_desc",
            "stk_callback_url",
        )
        widgets = FIELD_WIDGETS
        labels = DARAJA_LABELS
        help_texts = DARAJA_HELP

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._keep_secrets(instance)
        self._fill_empty(
            instance,
            stk_account_reference=SANDBOX_ACCOUNT_REF,
            stk_transaction_desc=SANDBOX_STK_DESC,
        )
        self._apply_callback_urls(instance, "stk_callback_url")
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DarajaBalanceForm(_DarajaFormBase):
    class Meta:
        model = DarajaConfig
        fields = (
            "initiator_name",
            "security_credential",
            "balance_identifier_type",
            "balance_remarks",
            "result_url",
            "timeout_url",
        )
        widgets = FIELD_WIDGETS
        labels = DARAJA_LABELS
        help_texts = DARAJA_HELP

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._keep_secrets(instance)
        self._fill_empty(instance, balance_remarks=SANDBOX_BALANCE_REMARKS)
        self._apply_callback_urls(instance, "result_url", "timeout_url")
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DarajaB2CForm(_DarajaFormBase):
    class Meta:
        model = DarajaConfig
        fields = ("b2c_enabled", "b2c_command_id", "b2c_occasion", "b2c_remarks")
        widgets = FIELD_WIDGETS
        labels = DARAJA_LABELS
        help_texts = DARAJA_HELP

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._fill_empty(
            instance,
            b2c_remarks=SANDBOX_B2C_REMARKS,
            b2c_occasion=SANDBOX_B2C_OCCASION,
        )
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DarajaB2BForm(_DarajaFormBase):
    class Meta:
        model = DarajaConfig
        fields = (
            "b2b_enabled",
            "b2b_sender_identifier_type",
            "b2b_paybill_command",
            "b2b_till_command",
            "b2b_remarks",
        )
        widgets = FIELD_WIDGETS
        labels = DARAJA_LABELS
        help_texts = DARAJA_HELP

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, request=request, **kwargs)
        # Pre-fill the usual Safaricom defaults so Advanced is ready without typing.
        if not self.is_bound:
            if not self.fields["b2b_sender_identifier_type"].initial and not getattr(
                self.instance, "b2b_sender_identifier_type", None
            ):
                self.fields["b2b_sender_identifier_type"].initial = DarajaConfig.IdentifierType.SHORTCODE
            if not getattr(self.instance, "b2b_paybill_command", None):
                self.fields["b2b_paybill_command"].initial = DarajaConfig.B2BCommand.PAYBILL
            if not getattr(self.instance, "b2b_till_command", None):
                self.fields["b2b_till_command"].initial = DarajaConfig.B2BCommand.BUY_GOODS
            if not (getattr(self.instance, "b2b_remarks", None) or "").strip():
                self.fields["b2b_remarks"].initial = SANDBOX_B2B_REMARKS

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Keep both payout paths ready whenever B2B is on — no extra fields required.
        if instance.b2b_enabled:
            if not instance.b2b_paybill_command:
                instance.b2b_paybill_command = DarajaConfig.B2BCommand.PAYBILL
            if not instance.b2b_till_command:
                instance.b2b_till_command = DarajaConfig.B2BCommand.BUY_GOODS
            if not instance.b2b_sender_identifier_type:
                instance.b2b_sender_identifier_type = DarajaConfig.IdentifierType.SHORTCODE
        self._fill_empty(instance, b2b_remarks=SANDBOX_B2B_REMARKS)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class DarajaAgentShopForm(_DarajaFormBase):
    class Meta:
        model = DarajaConfig
        fields = (
            "agent_shop_enabled",
            "agent_channel",
            "agent_till_number",
            "agent_head_office",
            "agent_store_number",
            "agent_operator_id",
            "agent_api_enabled",
            "agent_use_shared_app",
            "agent_consumer_key",
            "agent_consumer_secret",
            "agent_initiator_name",
            "agent_security_credential",
            "agent_api_base_url",
            "agent_deposit_path",
            "agent_withdraw_path",
            "agent_deposit_command",
            "agent_withdraw_command",
            "agent_deposit_callback_url",
            "agent_withdraw_callback_url",
            "agent_result_url",
            "agent_timeout_url",
            "agent_track_commission",
            "agent_api_notes",
            "agent_cash_in_enabled",
            "agent_cash_out_enabled",
            "agent_min_amount",
            "agent_max_amount",
            "agent_daily_limit",
            "agent_cash_in_fee",
            "agent_cash_out_fee",
            "agent_cash_in_account_ref",
            "agent_float_warn_kes",
            "agent_receipt_prefix",
        )
        widgets = FIELD_WIDGETS
        labels = DARAJA_LABELS
        help_texts = DARAJA_HELP

    def clean_agent_cash_in_account_ref(self):
        return (self.cleaned_data.get("agent_cash_in_account_ref") or "").strip()[:12]

    def clean_agent_receipt_prefix(self):
        return (self.cleaned_data.get("agent_receipt_prefix") or "").strip()[:16] or "AG"

    def clean_agent_till_number(self):
        return re.sub(r"\D", "", self.cleaned_data.get("agent_till_number") or "")

    def clean_agent_head_office(self):
        return re.sub(r"\D", "", self.cleaned_data.get("agent_head_office") or "")

    def clean_agent_deposit_path(self):
        path = (self.cleaned_data.get("agent_deposit_path") or "").strip()
        if path and not path.startswith("/"):
            path = "/" + path
        return path

    def clean_agent_withdraw_path(self):
        path = (self.cleaned_data.get("agent_withdraw_path") or "").strip()
        if path and not path.startswith("/"):
            path = "/" + path
        return path

    def clean(self):
        cleaned = super().clean()
        shop_on = bool(cleaned.get("agent_shop_enabled"))
        cash_in = bool(cleaned.get("agent_cash_in_enabled"))
        cash_out = bool(cleaned.get("agent_cash_out_enabled"))
        channel = cleaned.get("agent_channel") or DarajaConfig.AgentChannel.BUSINESS
        defaults = {
            "agent_min_amount": "10",
            "agent_max_amount": "70000",
            "agent_daily_limit": "0",
            "agent_cash_in_fee": "0",
            "agent_cash_out_fee": "0",
            "agent_float_warn_kes": "1000",
        }
        for name, fallback in defaults.items():
            if cleaned.get(name) is None:
                cleaned[name] = type(self.instance)._meta.get_field(name).to_python(fallback)
        min_amt = cleaned.get("agent_min_amount")
        max_amt = cleaned.get("agent_max_amount")
        if shop_on and not cash_in and not cash_out:
            self.add_error(
                "agent_cash_in_enabled",
                "Turn on deposit, withdraw, or both when agent shop is enabled.",
            )
        if min_amt is not None and max_amt is not None and min_amt > max_amt:
            self.add_error("agent_max_amount", "Maximum must be greater than or equal to the minimum.")
        if not cleaned.get("agent_receipt_prefix"):
            cleaned["agent_receipt_prefix"] = "AG"
        if shop_on and channel == DarajaConfig.AgentChannel.SAFARICOM:
            if cleaned.get("agent_api_enabled") and not cleaned.get("agent_till_number"):
                self.add_error("agent_till_number", "Enter the agent till number from Safaricom.")
            if cleaned.get("agent_api_enabled") and not cleaned.get("agent_use_shared_app"):
                if not (cleaned.get("agent_consumer_key") or getattr(self.instance, "agent_consumer_key", "")):
                    self.add_error("agent_consumer_key", "Paste the agent app consumer key, or reuse the shared Daraja app.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._keep_secrets(instance)
        self._fill_empty(instance, agent_cash_in_account_ref="AGENT", agent_receipt_prefix="AG")
        self._apply_callback_urls(
            instance,
            "agent_deposit_callback_url",
            "agent_withdraw_callback_url",
            "agent_result_url",
            "agent_timeout_url",
        )
        channel = self.cleaned_data.get("agent_channel") or DarajaConfig.AgentChannel.BUSINESS
        if (
            channel == DarajaConfig.AgentChannel.BUSINESS
            and self.cleaned_data.get("agent_shop_enabled")
            and self.cleaned_data.get("agent_cash_out_enabled")
        ):
            instance.b2c_enabled = True
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
    TYPE_PHONE = "PHONE"
    TYPE_PAYBILL = "PAYBILL"
    TYPE_TILL = "TILL"

    destination_type = forms.ChoiceField(
        label="Send to",
        choices=(
            (TYPE_PHONE, "Customer phone"),
            (TYPE_PAYBILL, "Paybill"),
            (TYPE_TILL, "Till (Buy Goods)"),
        ),
        widget=forms.Select(attrs={**SELECT, "id": "id_send_destination_type"}),
    )
    destination = forms.CharField(
        label="Where to send",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                **FIELD,
                "id": "id_send_destination",
                "autocomplete": "off",
                "placeholder": "Phone, paybill, or till",
            }
        ),
    )
    amount = forms.DecimalField(
        label="Amount (KES)",
        min_value=1,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={**FIELD, "min": "1", "step": "1", "id": "id_send_amount"}),
    )
    account_ref = forms.CharField(
        label="Account number",
        max_length=12,
        required=False,
        widget=forms.TextInput(
            attrs={
                **FIELD,
                "id": "id_send_account_ref",
                "placeholder": "Customer account on that paybill",
                "autocomplete": "off",
            }
        ),
        help_text="Only needed when sending to a paybill.",
    )

    def clean_destination(self):
        return re.sub(r"\D", "", self.cleaned_data.get("destination") or "")

    def clean_account_ref(self):
        return (self.cleaned_data.get("account_ref") or "").strip()

    def clean(self):
        cleaned = super().clean()
        dest_type = cleaned.get("destination_type")
        destination = cleaned.get("destination") or ""
        account_ref = cleaned.get("account_ref") or ""
        if not dest_type or not destination:
            return cleaned

        if dest_type == self.TYPE_PHONE:
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
                "That looks like a phone number. Choose Customer phone, or enter a shortcode / till.",
            )
            return cleaned
        if len(destination) < 5 or len(destination) > 8:
            label = "till" if dest_type == self.TYPE_TILL else "paybill"
            self.add_error("destination", f"Enter a valid {label} number (5–8 digits).")
            return cleaned
        if dest_type == self.TYPE_PAYBILL and not account_ref:
            self.add_error("account_ref", "Enter the account number for that paybill.")
        return cleaned

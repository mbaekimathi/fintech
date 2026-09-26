from django import forms

from integrations.models import DarajaConfig

FIELD = {"class": "field"}
SELECT = {"class": "select"}


class C2bSimulateForm(forms.Form):
    shortcode = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={**FIELD, "inputmode": "numeric", "placeholder": "e.g. 600000"}),
        label="Paybill / till shortcode",
    )
    amount = forms.DecimalField(
        min_value=1,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**FIELD, "min": "1", "step": "0.01"}),
        label="Amount (KES)",
    )
    bill_ref = forms.CharField(
        max_length=64,
        required=False,
        widget=forms.TextInput(
            attrs={
                **FIELD,
                "placeholder": "Use a monitor collection ID (auto-unique suffix if blank)",
            }
        ),
        label="Bill reference",
        help_text="Prefer a collection ID from Automations. Each simulate run gets a unique suffix to avoid Safaricom duplicate correlator errors.",
    )
    msisdn = forms.CharField(
        max_length=20,
        initial="254708374149",
        widget=forms.TextInput(attrs={**FIELD, "inputmode": "tel"}),
        label="Payer phone (sandbox)",
    )
    command_id = forms.ChoiceField(
        choices=(
            ("CustomerPayBillOnline", "Pay Bill"),
            ("CustomerBuyGoodsOnline", "Buy Goods (till)"),
        ),
        widget=forms.Select(attrs=SELECT),
        label="Payment type",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = DarajaConfig.load()
        if config.shortcode and not self.initial.get("shortcode"):
            self.initial["shortcode"] = config.shortcode

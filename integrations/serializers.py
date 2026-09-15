from rest_framework import serializers

from paybill.models import LedgerEntry, PaybillAccount


class LedgerEntrySerializer(serializers.ModelSerializer):
    paybill_number = serializers.CharField(required=False)

    class Meta:
        model = LedgerEntry
        fields = (
            "reference",
            "mpesa_reference",
            "paybill_number",
            "direction",
            "amount",
            "currency",
            "payer_name",
            "payer_phone",
            "account_ref",
            "status",
            "narrative",
            "raw_payload",
            "posted_at",
        )
        read_only_fields = ("posted_at",)
        extra_kwargs = {
            "reference": {"validators": []},
            "mpesa_reference": {"required": False, "allow_blank": True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["paybill_number"] = instance.paybill_account.paybill_number
        return data

    def validate_reference(self, value):
        if LedgerEntry.objects.filter(reference=value).exists():
            raise serializers.ValidationError("This reference is already on the ledger.")
        return value

    def create(self, validated_data):
        reference = (validated_data.get("reference") or "").strip()
        mpesa_reference = (validated_data.get("mpesa_reference") or "").strip()
        if not mpesa_reference and reference:
            validated_data["mpesa_reference"] = reference[:64]
        return super().create(validated_data)

    def validate(self, attrs):
        number = attrs.pop("paybill_number", None)
        if not number:
            raise serializers.ValidationError({"paybill_number": "This field is required."})
        system = self.context["system"]
        try:
            account = PaybillAccount.objects.get(
                paybill_number=number,
                is_active=True,
                connected_system=system,
            )
        except PaybillAccount.DoesNotExist:
            raise serializers.ValidationError(
                {"paybill_number": "No active paybill account is mapped to this system."}
            )
        attrs["paybill_account"] = account
        attrs["connected_system"] = system
        return attrs

"""STK collection on behalf of hub or per-account Daraja credentials."""

from __future__ import annotations

from integrations.daraja import callback_urls
from integrations.daraja_client import DarajaClient, DarajaError
from integrations.models import DarajaConfig, DarajaOperation
from paybill.models import CollectionMonitor


def initiate_monitor_stk_collection(
    *,
    monitor: CollectionMonitor,
    phone: str,
    amount,
    request,
    created_by=None,
) -> DarajaOperation:
    if not monitor.stk_ready():
        raise DarajaError(
            "STK is not ready for this account. Finish hub Daraja STK setup or add this account's credentials."
        )
    monitor.ensure_ledger_paybill_account()
    config = DarajaConfig.load()
    client = DarajaClient(config, monitor=monitor)
    urls = callback_urls(request)
    callback = urls.get("stk_callback_url") or config.stk_callback_url
    body, payload = client.stk_push(
        phone=phone,
        amount=amount,
        account_ref=monitor.stk_account_reference(),
        callback_url=callback,
        transaction_type=monitor.stk_transaction_type(),
        party_b=monitor.stk_party_b(),
        transaction_desc=(monitor.label or "Payment")[:13],
    )
    return DarajaOperation.objects.create(
        kind=DarajaOperation.Kind.STK,
        status=DarajaOperation.Status.QUEUED,
        destination=str(payload.get("PhoneNumber") or phone)[:32],
        amount=amount,
        account_ref=monitor.stk_account_reference(),
        collection_monitor=monitor,
        merchant_request_id=body.get("MerchantRequestID") or "",
        checkout_request_id=body.get("CheckoutRequestID") or "",
        summary=body.get("CustomerMessage") or "Check your phone for the M-Pesa PIN prompt.",
        request_payload=payload,
        response_payload=body,
        created_by=created_by,
    )

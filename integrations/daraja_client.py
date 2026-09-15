"""Safaricom Daraja HTTP client for STK, account balance, B2C, and B2B."""

from __future__ import annotations

import base64
import json
import re
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from integrations.daraja import PRODUCTION_OAUTH_URL, SANDBOX_OAUTH_URL
from integrations.security_credential import CredentialError, encrypt_security_credential

SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
PRODUCTION_BASE = "https://api.safaricom.co.ke"


class DarajaError(Exception):
    def __init__(self, message: str, payload: dict | None = None):
        super().__init__(message)
        self.payload = payload or {}


def kenya_msisdn(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if len(digits) == 9:
        return "254" + digits
    raise DarajaError("Enter a Kenyan mobile number such as 07XXXXXXXX or 2547XXXXXXXX.")


def whole_kes(amount) -> int:
    value = Decimal(str(amount))
    if value < 1:
        raise DarajaError("Amount must be at least KES 1.")
    return int(value)


def _stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f"{shortcode}{passkey}{timestamp}".encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _json_request(url: str, *, headers: dict, payload: dict | None = None, method: str = "POST"):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"User-Agent": "NEXUS-Ledger/1.0", **headers}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8") or "{}"
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"errorMessage": raw[:400] or f"HTTP {exc.code}"}
        return exc.code, parsed
    except Exception as exc:
        raise DarajaError(f"Could not reach Daraja: {exc}") from exc


def _error_message(payload: dict) -> str:
    return (
        payload.get("errorMessage")
        or payload.get("ResponseDescription")
        or payload.get("CustomerMessage")
        or payload.get("error_description")
        or payload.get("requestId")
        or "Daraja rejected the request."
    )


class DarajaClient:
    def __init__(self, config):
        self.config = config
        self._token = None

    @property
    def sandbox(self) -> bool:
        return str(self.config.environment) == "SANDBOX"

    @property
    def base_url(self) -> str:
        return SANDBOX_BASE if self.sandbox else PRODUCTION_BASE

    def _security_credential(self) -> str:
        try:
            return encrypt_security_credential(
                self.config.security_credential or "",
                sandbox=self.sandbox,
            )
        except CredentialError as exc:
            raise DarajaError(str(exc)) from exc

    def _payout_party_a(self, *, identifier: str | None = None) -> str:
        identifier = str(identifier or self.config.balance_identifier_type or "4")
        if identifier == "2":
            party_a = (self.config.till_number or "").strip()
        else:
            party_a = self.config.payout_shortcode
        if not party_a:
            raise DarajaError(
                "Set the organization shortcode (sandbox Party A is 600996) before balance or payouts."
            )
        return party_a

    def access_token(self) -> str:
        if self._token:
            return self._token
        key = (self.config.consumer_key or "").strip()
        secret = (self.config.consumer_secret or "").strip()
        if not key or not secret:
            raise DarajaError("Save a consumer key and consumer secret on Daraja setup first.")
        url = SANDBOX_OAUTH_URL if self.sandbox else PRODUCTION_OAUTH_URL
        basic = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
        status, body = _json_request(
            url,
            headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
            method="GET",
        )
        token = (body or {}).get("access_token")
        if status >= 400 or not token:
            raise DarajaError(_error_message(body), body)
        self._token = token
        return token

    def _post(self, path: str, payload: dict) -> dict:
        status, body = _json_request(
            self.base_url + path,
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            payload=payload,
        )
        if status >= 400:
            raise DarajaError(_error_message(body), body)
        code = str(body.get("ResponseCode", "0"))
        if code not in {"0", "00"}:
            raise DarajaError(_error_message(body), body)
        return body

    def _callback(self, stored: str, fallback: str) -> str:
        from integrations.daraja import _is_public_https, callback_urls

        blob = f"{stored} {fallback}"
        urls = callback_urls()
        if "stk/callback" in blob:
            live = urls.get("stk_callback_url", "")
        elif "timeout" in blob:
            live = urls.get("timeout_url", "")
        else:
            live = urls.get("result_url", "")
        if _is_public_https(live):
            return live
        for candidate in ((stored or "").strip(), (fallback or "").strip()):
            if _is_public_https(candidate):
                return candidate
        raise DarajaError(
            "CallBackURL must be public HTTPS. Keep ngrok running (ngrok http 8000), "
            "then try again. Optional: set DARAJA_PUBLIC_BASE_URL in .env to your ngrok https URL."
        )

    def stk_push(self, *, phone: str, amount, account_ref: str, callback_url: str) -> dict:
        if not self.config.stk_ready:
            raise DarajaError("STK is not ready. Save passkey, shortcode, and callback URL on Daraja setup.")
        msisdn = kenya_msisdn(phone)
        shortcode = (self.config.shortcode or "").strip()
        tx_type = self.config.stk_transaction_type or "CustomerPayBillOnline"
        party_b = (self.config.till_number or shortcode).strip() if tx_type == "CustomerBuyGoodsOnline" else shortcode
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        payload = {
            "BusinessShortCode": shortcode,
            "Password": _stk_password(shortcode, self.config.passkey, timestamp),
            "Timestamp": timestamp,
            "TransactionType": tx_type,
            "Amount": whole_kes(amount),
            "PartyA": msisdn,
            "PartyB": party_b,
            "PhoneNumber": msisdn,
            "CallBackURL": self._callback(self.config.stk_callback_url, callback_url),
            "AccountReference": (account_ref or self.config.stk_account_reference or "NEXUS")[:12],
            "TransactionDesc": (self.config.stk_transaction_desc or "Payment")[:13],
        }
        return self._post("/mpesa/stkpush/v1/processrequest", payload), payload

    def stk_query(self, checkout_request_id: str) -> dict:
        shortcode = (self.config.shortcode or "").strip()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        payload = {
            "BusinessShortCode": shortcode,
            "Password": _stk_password(shortcode, self.config.passkey, timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        return self._post("/mpesa/stkpushquery/v1/query", payload)

    def account_balance(self, *, result_url: str, timeout_url: str, identifier: str | None = None):
        if not self.config.balance_ready:
            raise DarajaError("Balance is not ready. Save initiator, security credential, and result URLs.")
        identifier = str(identifier or self.config.balance_identifier_type or "4")
        party_a = self._payout_party_a(identifier=identifier)
        payload = {
            "Initiator": self.config.initiator_name,
            "SecurityCredential": self._security_credential(),
            "CommandID": "AccountBalance",
            "PartyA": party_a,
            "IdentifierType": identifier,
            "Remarks": (self.config.balance_remarks or "Balance")[:100],
            "QueueTimeOutURL": self._callback(self.config.timeout_url, timeout_url),
            "ResultURL": self._callback(self.config.result_url, result_url),
        }
        return self._post("/mpesa/accountbalance/v1/query", payload), payload, party_a

    def b2c_send(self, *, phone: str, amount, result_url: str, timeout_url: str) -> dict:
        if not self.config.b2c_ready:
            raise DarajaError("Phone payout is not enabled. Turn on B2C on Daraja setup.")
        msisdn = kenya_msisdn(phone)
        occasion = (self.config.b2c_occasion or "Payment")[:100]
        payload = {
            "OriginatorConversationID": str(uuid.uuid4()),
            "InitiatorName": self.config.initiator_name,
            "SecurityCredential": self._security_credential(),
            "CommandID": self.config.b2c_command_id or "BusinessPayment",
            "Amount": whole_kes(amount),
            "PartyA": self._payout_party_a(),
            "PartyB": msisdn,
            "Remarks": (self.config.b2c_remarks or "Payout")[:100],
            "QueueTimeOutURL": self._callback(self.config.timeout_url, timeout_url),
            "ResultURL": self._callback(self.config.result_url, result_url),
            "Occasion": occasion,
            "Occassion": occasion,
        }
        try:
            return self._post("/mpesa/b2c/v3/paymentrequest", payload), payload, msisdn
        except DarajaError:
            return self._post("/mpesa/b2c/v1/paymentrequest", payload), payload, msisdn

    def b2b_send(
        self,
        *,
        destination: str,
        amount,
        to_till: bool,
        account_ref: str,
        result_url: str,
        timeout_url: str,
    ) -> dict:
        if not self.config.b2b_ready:
            raise DarajaError("Paybill/till payout is not enabled. Turn on B2B on Daraja setup.")
        dest = re.sub(r"\D", "", destination or "")
        if dest.startswith("254") or len(dest) >= 10:
            raise DarajaError(
                "Enter a paybill or till shortcode, not a phone number. Use Customer phone to pay a mobile."
            )
        if len(dest) < 5 or len(dest) > 8:
            raise DarajaError("Enter the destination paybill or till number (5–8 digits).")
        command = self.config.b2b_till_command if to_till else self.config.b2b_paybill_command
        receiver_type = "2" if to_till else "4"
        # Paybill B2B needs an account reference. Till (Buy Goods) does not — keep a short fallback.
        if to_till:
            reference = (account_ref or self.config.stk_account_reference or "NEXUS")[:12]
        else:
            reference = (account_ref or "").strip()
            if not reference:
                raise DarajaError("Enter the account number for that paybill.")
            reference = reference[:12]
        payload = {
            "Initiator": self.config.initiator_name,
            "SecurityCredential": self._security_credential(),
            "CommandID": command or ("BusinessBuyGoods" if to_till else "BusinessPayBill"),
            "SenderIdentifierType": str(self.config.b2b_sender_identifier_type or "4"),
            "RecieverIdentifierType": receiver_type,
            "Amount": whole_kes(amount),
            "PartyA": self._payout_party_a(),
            "PartyB": dest,
            "AccountReference": reference,
            "Remarks": (self.config.b2b_remarks or "Transfer")[:100],
            "QueueTimeOutURL": self._callback(self.config.timeout_url, timeout_url),
            "ResultURL": self._callback(self.config.result_url, result_url),
        }
        return self._post("/mpesa/b2b/v1/paymentrequest", payload), payload, dest

"""User-facing explanations for common Daraja API failures."""

from __future__ import annotations

INITIATOR_NOT_ALLOWED = "the initiator is not allowed to initiate this request"

_INITIATOR_HINTS = {
    "utility": (
        "Safaricom rejected this initiator for utility-to-working transfers. "
        "Use the live API initiator from your M-Pesa Business portal (not sandbox testapi), "
        "ask Safaricom to assign the ORG B2B API Initiator role to that user, "
        "then re-paste the initiator password on Daraja setup under Balance & initiator."
    ),
    "b2b": (
        "Safaricom rejected this initiator for B2B payouts. "
        "Confirm the initiator username and password on Daraja setup match your M-Pesa Business portal, "
        "and ask Safaricom to enable the ORG B2B API Initiator role for that API user."
    ),
    "b2c": (
        "Safaricom rejected this initiator for phone payouts. "
        "Ask Safaricom to assign the ORG B2C API Initiator role to your API user, "
        "then confirm the initiator username and password on Daraja setup."
    ),
    "balance": (
        "Safaricom rejected this initiator for balance queries. "
        "Confirm the initiator username and password on Daraja setup match Daraja Test credentials "
        "in sandbox, or your live M-Pesa Business portal API user in production."
    ),
    "default": (
        "Safaricom rejected this initiator for the request. "
        "Confirm the initiator username and password on Daraja setup, "
        "and ask Safaricom to enable the correct API initiator role for this paybill."
    ),
}


def explain_daraja_error(message: str, *, context: str = "default") -> str:
    text = (message or "").strip()
    if not text:
        return _INITIATOR_HINTS.get(context, _INITIATOR_HINTS["default"])
    if INITIATOR_NOT_ALLOWED in text.lower():
        return _INITIATOR_HINTS.get(context, _INITIATOR_HINTS["default"])
    return text


def utility_transfer_blockers(config) -> list[str]:
    """Checks NEXUS can detect before calling Safaricom for utility → working."""
    blockers: list[str] = []
    if not config.b2b_enabled:
        blockers.append("Turn on B2B on Daraja setup → Payouts.")
    if not config.balance_ready:
        blockers.append("Finish Balance & initiator on Daraja setup first.")

    initiator = (config.initiator_name or "").strip()
    org = (config.org_shortcode or "").strip()
    sandbox = str(config.environment) == "SANDBOX"

    if sandbox:
        if initiator and initiator.lower() != "testapi":
            blockers.append(
                "Sandbox utility transfers expect initiator testapi from Daraja Test credentials."
            )
        if org and org != "600996":
            blockers.append("Sandbox Party A / organization shortcode should be 600996 for float moves.")
    else:
        if initiator.lower() in {"", "testapi"}:
            blockers.append(
                "Production needs your live M-Pesa Business API initiator — not sandbox testapi."
            )
        if not org:
            blockers.append(
                "Set organization shortcode to your live paybill number on Daraja setup."
            )
    return blockers

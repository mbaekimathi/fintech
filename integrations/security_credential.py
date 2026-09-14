"""Encrypt Daraja initiator passwords with Safaricom's public certificates."""

from __future__ import annotations

import base64
from pathlib import Path

CERT_DIR = Path(__file__).resolve().parent / "certs"


class CredentialError(Exception):
    pass


def looks_encrypted(value: str) -> bool:
    raw = (value or "").strip()
    if len(raw) < 80:
        return False
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        return False
    return len(decoded) >= 64


def encrypt_security_credential(password: str, *, sandbox: bool) -> str:
    raw = (password or "").strip()
    if not raw:
        raise CredentialError("Save the initiator password on Daraja setup first.")
    if looks_encrypted(raw):
        return raw
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise CredentialError(
            "Install the cryptography package so NEXUS can encrypt the initiator password."
        ) from exc
    name = "sandbox.cer" if sandbox else "production.cer"
    pem = (CERT_DIR / name).read_bytes()
    cert = x509.load_pem_x509_certificate(pem)
    encrypted = cert.public_key().encrypt(raw.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode("ascii")

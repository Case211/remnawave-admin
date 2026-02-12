"""DKIM key management and email signing."""
import base64
import logging
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


def generate_dkim_keypair() -> Tuple[str, str]:
    """Generate an RSA-2048 key pair for DKIM signing.

    Returns (private_pem, public_pem) as strings.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def sign_message(raw_message: bytes, domain: str, selector: str, private_key_pem: str) -> bytes:
    """Add a DKIM-Signature header to a raw email message.

    Returns the signed message bytes.
    """
    try:
        import dkim
        signed = dkim.sign(
            message=raw_message,
            selector=selector.encode(),
            domain=domain.encode(),
            privkey=private_key_pem.encode(),
            include_headers=[b"From", b"To", b"Subject", b"Date", b"Message-ID", b"MIME-Version", b"Content-Type"],
        )
        return signed + raw_message
    except Exception as e:
        logger.error("DKIM signing failed for %s: %s", domain, e)
        return raw_message


def get_dkim_dns_record(selector: str, public_key_pem: str) -> str:
    """Build the DNS TXT record value for a DKIM public key.

    Returns the value to set on ``selector._domainkey.domain``.
    """
    lines = public_key_pem.strip().split("\n")
    # Strip PEM header/footer
    key_data = "".join(line for line in lines if not line.startswith("-----"))
    return f"v=DKIM1; k=rsa; p={key_data}"


def get_public_key_base64(public_key_pem: str) -> str:
    """Extract raw base64 key data from PEM."""
    lines = public_key_pem.strip().split("\n")
    return "".join(line for line in lines if not line.startswith("-----"))

"""DNS record verification for mail server setup."""
import logging
import socket
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DnsRecord:
    record_type: str  # MX, TXT
    host: str
    value: str
    purpose: str  # MX, SPF, DKIM, DMARC
    is_configured: bool = False
    current_value: Optional[str] = None


def _resolve(qname: str, rdtype: str) -> List[str]:
    """Resolve DNS records using dnspython."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(qname, rdtype)
        return [str(rdata) for rdata in answers]
    except Exception:
        return []


def check_mx_records(domain: str) -> Tuple[bool, List[str]]:
    """Check if MX records exist for the domain."""
    records = _resolve(domain, "MX")
    return (len(records) > 0, records)


def check_spf_record(domain: str, server_ip: str) -> Tuple[bool, Optional[str]]:
    """Check if SPF TXT record includes the server IP."""
    txt_records = _resolve(domain, "TXT")
    for rec in txt_records:
        val = rec.strip('"')
        if val.startswith("v=spf1"):
            ok = server_ip in val or "include:" in val or "+all" in val
            return (ok, val)
    return (False, None)


def check_dkim_record(domain: str, selector: str) -> Tuple[bool, Optional[str]]:
    """Check if DKIM TXT record exists for selector._domainkey.domain."""
    qname = f"{selector}._domainkey.{domain}"
    txt_records = _resolve(qname, "TXT")
    for rec in txt_records:
        val = rec.strip('"')
        if "v=DKIM1" in val or "k=rsa" in val:
            return (True, val)
    return (False, txt_records[0].strip('"') if txt_records else None)


def check_dmarc_record(domain: str) -> Tuple[bool, Optional[str]]:
    """Check if DMARC TXT record exists at _dmarc.domain."""
    qname = f"_dmarc.{domain}"
    txt_records = _resolve(qname, "TXT")
    for rec in txt_records:
        val = rec.strip('"')
        if val.startswith("v=DMARC1"):
            return (True, val)
    return (False, None)


def check_ptr_record(server_ip: str, expected_domain: str) -> Tuple[bool, Optional[str]]:
    """Check if the server IP has a PTR record pointing to the expected domain."""
    try:
        import dns.resolver
        import dns.reversename
        rev_name = dns.reversename.from_address(server_ip)
        answers = dns.resolver.resolve(rev_name, "PTR")
        ptr_values = [str(rdata).rstrip(".") for rdata in answers]
        # Check if any PTR record matches or is a subdomain of the expected domain
        for ptr in ptr_values:
            if ptr == expected_domain or ptr.endswith(f".{expected_domain}"):
                return (True, ptr)
        # PTR exists but doesn't match the domain
        return (False, ", ".join(ptr_values))
    except Exception:
        return (False, None)


def get_server_ip() -> str:
    """Detect the server's public IP address."""
    try:
        import httpx
        resp = httpx.get("https://api.ipify.org", timeout=5)
        return resp.text.strip()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "YOUR_SERVER_IP"


def get_required_dns_records(
    domain: str,
    selector: str,
    public_key_pem: str,
    server_ip: Optional[str] = None,
) -> List[DnsRecord]:
    """Return all required DNS records with their current configuration status."""
    if not server_ip:
        server_ip = get_server_ip()

    from web.backend.core.mail.dkim_manager import get_dkim_dns_record
    dkim_value = get_dkim_dns_record(selector, public_key_pem)

    records: List[DnsRecord] = []

    # MX record
    mx_ok, mx_vals = check_mx_records(domain)
    records.append(DnsRecord(
        record_type="MX",
        host=domain,
        value=f"10 {domain}.",
        purpose="MX",
        is_configured=mx_ok,
        current_value=", ".join(mx_vals) if mx_vals else None,
    ))

    # SPF record
    spf_ok, spf_val = check_spf_record(domain, server_ip)
    records.append(DnsRecord(
        record_type="TXT",
        host=domain,
        value=f"v=spf1 ip4:{server_ip} -all",
        purpose="SPF",
        is_configured=spf_ok,
        current_value=spf_val,
    ))

    # DKIM record
    dkim_ok, dkim_current = check_dkim_record(domain, selector)
    records.append(DnsRecord(
        record_type="TXT",
        host=f"{selector}._domainkey.{domain}",
        value=dkim_value,
        purpose="DKIM",
        is_configured=dkim_ok,
        current_value=dkim_current,
    ))

    # DMARC record
    dmarc_ok, dmarc_val = check_dmarc_record(domain)
    records.append(DnsRecord(
        record_type="TXT",
        host=f"_dmarc.{domain}",
        value=f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}",
        purpose="DMARC",
        is_configured=dmarc_ok,
        current_value=dmarc_val,
    ))

    # PTR (reverse DNS) record
    ptr_ok, ptr_val = check_ptr_record(server_ip, domain)
    records.append(DnsRecord(
        record_type="PTR",
        host=server_ip,
        value=f"mail.{domain}",
        purpose="PTR",
        is_configured=ptr_ok,
        current_value=ptr_val,
    ))

    return records

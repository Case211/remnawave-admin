"""DNS record verification for mail server setup."""
import logging
import socket
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Public recursive resolvers — bypass local DNS cache so admin panel always sees
# authoritative current records instead of stale values cached for hours/days.
PUBLIC_NAMESERVERS = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]


def _get_resolver():
    """Return a dnspython Resolver configured to query public nameservers directly."""
    import dns.resolver
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = PUBLIC_NAMESERVERS
    r.timeout = 3.0
    r.lifetime = 5.0
    r.cache = None
    return r


def _resolve(qname: str, rdtype: str) -> List[str]:
    """Resolve DNS records via public recursive resolvers (no local cache)."""
    try:
        resolver = _get_resolver()
        answers = resolver.resolve(qname, rdtype)
        return [str(rdata) for rdata in answers]
    except Exception:
        return []


@dataclass
class DnsRecord:
    record_type: str  # MX, TXT
    host: str
    value: str
    purpose: str  # MX, SPF, DKIM, DMARC
    is_configured: bool = False
    current_value: Optional[str] = None


def check_mx_records(domain: str, server_ip: str = "",
                     expected_host: str = "") -> Tuple[bool, List[str]]:
    """Проверить, что почта домена приходит именно к нам.

    Раньше здесь стояло `len(records) > 0`, и любая MX-запись считалась
    правильной настройкой. На домене, переехавшем от старого хостера, это
    выглядело так: галка «MX ✓» горит зелёным, а вся входящая почта уходит
    к прежнему провайдеру и отбивается там с «550 Disabled». Полгода можно
    не замечать.

    Сверяем по IP, а не по имени хоста: MX вправе называться как угодно —
    важно, что он резолвится в адрес этого сервера.
    """
    records = _resolve(domain, "MX")
    if not records:
        return (False, [])

    hosts = [rec.split()[-1].rstrip(".").lower() for rec in records if rec.split()]

    if expected_host and expected_host.rstrip(".").lower() in hosts:
        return (True, records)

    if server_ip:
        for host in hosts:
            if server_ip in _resolve(host, "A"):
                return (True, records)
        return (False, records)

    # Не с чем сравнивать — довольствуемся самим фактом наличия записи.
    return (True, records)


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
        import dns.reversename
        rev_name = dns.reversename.from_address(server_ip)
        resolver = _get_resolver()
        answers = resolver.resolve(rev_name, "PTR")
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
    mail_host = f"mail.{domain}"

    # A record for the mail host — без него MX указывает в пустоту
    mail_a = _resolve(mail_host, "A")
    records.append(DnsRecord(
        record_type="A",
        host=mail_host,
        value=server_ip,
        purpose="A",
        is_configured=server_ip in mail_a,
        current_value=", ".join(mail_a) if mail_a else None,
    ))

    mx_ok, mx_vals = check_mx_records(domain, server_ip=server_ip, expected_host=mail_host)
    records.append(DnsRecord(
        record_type="MX",
        host=domain,
        # Отдельное имя, а не сам домен: апекс часто занят A-записью сайта,
        # и на него же нельзя выписать PTR почтового сервера.
        value=f"10 {mail_host}.",
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

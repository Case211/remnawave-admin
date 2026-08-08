"""TLS для почтовых портов.

Приём и отправка почты жили без шифрования вовсе. Для входящих это значит,
что письмо идёт по интернету открытым текстом и получатель видит у нас в
заголовках отсутствие TLS; для порта отправки (587) — что пароль от релея
передаётся в base64, то есть фактически как есть.

Сертификат берётся по указанному в настройках пути. Если его нет, модуль
выписывает самоподписанный: для доставки между почтовыми серверами это
нормально — практически все MTA шифруют соединение, не проверяя сертификат
(наша собственная отправка в outbound_queue делает ровно так же). А вот для
порта 587 самоподписанный сертификат почтовый клиент покажет с руганью,
поэтому туда лучше положить настоящий — путь настраивается.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import ssl
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_CERT_DIR = "/app/certs"
_SELF_SIGNED_DAYS = 3650

_cached_context: Optional[ssl.SSLContext] = None
_cached_source: Optional[str] = None


def _config(key: str, default):
    try:
        from shared.config_service import config_service
        return config_service.get(key, default)
    except Exception:
        return default


def _generate_self_signed(cert_path: Path, key_path: Path, hostname: str) -> bool:
    """Выписать самоподписанный сертификат. True, если получилось."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])
        now = _dt.datetime.now(_dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _dt.timedelta(minutes=5))
            .not_valid_after(now + _dt.timedelta(days=_SELF_SIGNED_DAYS))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .sign(key, hashes.SHA256())
        )

        cert_path.parent.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        # Приватный ключ не должен читаться кем попало — том общий с логами
        # и бэкапами, куда заглядывают и другие процессы.
        os.chmod(key_path, 0o600)
        logger.info("Generated self-signed mail certificate for %s at %s", hostname, cert_path)
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to generate self-signed certificate: %s", e)
        return False


def get_tls_context(hostname: str = "localhost") -> Optional[ssl.SSLContext]:
    """Контекст для STARTTLS или None, если сертификата раздобыть не вышло.

    None — не аварийная ситуация: приём почты продолжает работать без
    шифрования, как и раньше. Вызывающий сам решает, насколько это терпимо
    для его порта.
    """
    global _cached_context, _cached_source

    cert_path = str(_config("mailserver_tls_cert_path", "") or "").strip()
    key_path = str(_config("mailserver_tls_key_path", "") or "").strip()
    source = f"{cert_path}|{key_path}|{hostname}"

    if _cached_context is not None and _cached_source == source:
        return _cached_context

    if cert_path and key_path:
        cert, key = Path(cert_path), Path(key_path)
        if not (cert.exists() and key.exists()):
            logger.warning("Mail TLS certificate not found at %s / %s", cert_path, key_path)
            return None
    else:
        cert_dir = Path(_config("mailserver_cert_dir", _DEFAULT_CERT_DIR))
        cert, key = cert_dir / "mail.crt", cert_dir / "mail.key"
        if not (cert.exists() and key.exists()):
            if not _generate_self_signed(cert, key, hostname):
                return None

    try:
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=str(cert), keyfile=str(key))
        # Старые почтовые серверы до сих пор ходят с TLS 1.0/1.1; для
        # оппортунистического шифрования между MTA это всё равно лучше, чем
        # открытый текст, но ниже 1.2 не опускаемся — иначе шифрование
        # становится декоративным.
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        _cached_context, _cached_source = context, source
        logger.info("Mail TLS enabled (cert=%s)", cert)
        return context
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to load mail TLS certificate: %s", e)
        return None


def reset_cache() -> None:
    """Сбросить кэш — после смены путей в настройках или обновления файла."""
    global _cached_context, _cached_source
    _cached_context = None
    _cached_source = None

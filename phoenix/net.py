"""URL safety and identifier helpers shared across proxy, panels, and Home Assistant integrations."""

import ipaddress
import re
import socket
from urllib.parse import urlsplit

_BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")
HA_ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def is_valid_ha_entity_id(entity_id: str) -> bool:
    """Validate a Home Assistant entity ID (e.g. 'sensor.living_room_temperature')."""
    return isinstance(entity_id, str) and HA_ENTITY_ID_RE.fullmatch(entity_id) is not None


def _normalize_ip(addr: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    ip = ipaddress.ip_address(addr)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_public_ip(addr: str) -> bool:
    return _normalize_ip(addr).is_global


def _is_allowed_private_ip(addr: str) -> bool:
    """Allow public and private LAN IPs while still blocking loopback, link-local/metadata, unspecified, and multicast."""
    ip = _normalize_ip(addr)
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        return False
    return True


def validate_proxy_url(url: str, allowed_hosts: str = "") -> None:
    """Reject non-HTTP(S) URLs, private/link-local/loopback targets, and non-allowlisted hosts."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Proxy only allows http and https URLs")
    if parsed.username or parsed.password:
        raise ValueError("Proxy URLs must not include credentials")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("Proxy URL requires a hostname")
    if hostname == "localhost" or hostname.endswith(_BLOCKED_HOST_SUFFIXES):
        raise ValueError("Proxy target host is not allowed")

    allowlist = {h.strip().lower().rstrip(".") for h in allowed_hosts.split(",") if h.strip()}
    if allowlist and hostname not in allowlist:
        raise ValueError("Proxy target host is not in proxy_allowed_hosts")

    try:
        if not _is_public_ip(hostname):
            raise ValueError("Proxy target IP must be publicly routable")
        return
    except ValueError as exc:
        if "publicly routable" in str(exc):
            raise

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Unable to resolve proxy target host") from exc
    if not infos:
        raise ValueError("Unable to resolve proxy target host")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise ValueError("Proxy target resolves to a non-public IP address")


def validate_panel_url(url: str, *, allow_private: bool = False) -> None:
    """Validate an HTTP panel data-source URL against SSRF rules.

    When allow_private is False (default), enforces the same public-only SSRF policy as /proxy.
    When allow_private is True, permits private LAN targets (e.g. local Prometheus/Grafana)
    while still blocking non-HTTP(S) schemes, embedded credentials, loopback, and link-local/metadata IPs.
    """
    if not allow_private:
        validate_proxy_url(url)
        return

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Panel HTTP source only allows http and https URLs")
    if parsed.username or parsed.password:
        raise ValueError("Panel HTTP source URLs must not include credentials")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("Panel HTTP source URL requires a hostname")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Panel HTTP source target host is not allowed")

    try:
        if not _is_allowed_private_ip(hostname):
            raise ValueError("Panel HTTP source target IP is not allowed")
        return
    except ValueError as exc:
        if "not allowed" in str(exc):
            raise

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Unable to resolve panel HTTP source host") from exc
    if not infos:
        raise ValueError("Unable to resolve panel HTTP source host")
    for info in infos:
        if not _is_allowed_private_ip(info[4][0]):
            raise ValueError("Panel HTTP source resolves to a disallowed IP address")

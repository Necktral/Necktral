from __future__ import annotations

import hmac
import ipaddress
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied


@dataclass(frozen=True)
class BootstrapGuardConfig:
    require_token: bool
    expected_token: Optional[str]
    ip_allowlist: list[str]


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _ip_allowed(ip_str: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for cidr in allowlist:
        net = ipaddress.ip_network(cidr.strip(), strict=False)
        if ip in net:
            return True
    return False


def bootstrap_guard_config() -> BootstrapGuardConfig:
    require = getattr(settings, "INITIAL_SETUP_REQUIRE_TOKEN", True)
    token = getattr(settings, "INITIAL_SETUP_TOKEN", None)
    allow = getattr(settings, "INITIAL_SETUP_IP_ALLOWLIST", [])
    return BootstrapGuardConfig(require_token=require, expected_token=token, ip_allowlist=allow)


def enforce_bootstrap_guard(request) -> None:
    cfg = bootstrap_guard_config()

    client_ip = _get_client_ip(request)
    if not _ip_allowed(client_ip, cfg.ip_allowlist):
        raise PermissionDenied("IP no autorizada para bootstrap.")

    if cfg.require_token:
        presented = request.headers.get("X-Setup-Token") or ""
        expected = cfg.expected_token or ""
        if not expected or not hmac.compare_digest(presented, expected):
            raise AuthenticationFailed("Token de instalacion invalido.")

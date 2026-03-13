"""Custom DRF permission classes for the sync_engine module.

These replace raw ``AllowAny`` on endpoints that implement their own
authentication logic (device enrollment codes, Ed25519 device signatures).

Using explicit permission classes instead of ``AllowAny`` provides:
  - Clearer documentation at the view level about why DRF auth is bypassed.
  - A single grep-able permission name for audit / code-review purposes.
  - An obvious place to add future restrictions (IP allow-lists, feature flags).
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsEnrollmentCode(BasePermission):
    """Grant access to the device-enrollment endpoint.

    This endpoint authenticates via a one-time enrollment code validated
    inside the view body — DRF-level ``IsAuthenticated`` is intentionally
    bypassed.  Rate-limiting (``auth_sensitive`` scope) and code expiry
    provide the security boundary.
    """

    message = "Enrollment endpoint — autenticación por código de enrolamiento."

    def has_permission(self, request, view) -> bool:  # noqa: ARG002
        return True


class IsDeviceAuthenticated(BasePermission):
    """Grant access to the sync-batch endpoint.

    This endpoint authenticates devices by verifying Ed25519 signatures
    attached to each command.  DRF-level JWT authentication is not
    applicable because the callers are offline-capable devices, not
    browser sessions.

    The actual cryptographic verification happens inside
    ``services.process_batch`` → ``verify_ed25519_signature``.
    """

    message = "Sync batch endpoint — autenticación por firma de dispositivo."

    def has_permission(self, request, view) -> bool:  # noqa: ARG002
        return True

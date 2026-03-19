"""Legacy compatibility re-exports for auth serializers."""

from apps.modulos.iam.serializers import BootstrapInitAdminSerializer as BootstrapInitSerializer
from apps.modulos.org.serializers import BootstrapOrganizationSerializer as BootstrapOrgSerializer
from modulos.auth_kernel.serializers import (
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    TwoFactorSetupConfirmSerializer,
    TwoFactorVerifySerializer,
)

__all__ = [
    "LoginSerializer",
    "MeSerializer",
    "BootstrapInitSerializer",
    "BootstrapOrgSerializer",
    "PasswordChangeSerializer",
    "TwoFactorSetupConfirmSerializer",
    "TwoFactorVerifySerializer",
]

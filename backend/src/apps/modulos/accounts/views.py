"""Legacy compatibility re-exports.

La implementación canónica de auth vive en `kernels.auth_kernel`.
`apps.accounts` mantiene solo identidad persistente y compat técnica.
"""

from kernels.auth_kernel.views import (
    LegacyBootstrapInitView as BootstrapInitView,
    LegacyBootstrapOrgView as BootstrapOrgView,
    LegacyBootstrapStatusView as BootstrapStatusView,
    LoginView,
    LogoutView,
    MeACLView,
    MeView,
    PasswordChangeView,
    RefreshView,
    TwoFactorConfirmView,
    TwoFactorDisableView,
    TwoFactorSetupView,
    TwoFactorVerifyView,
)

__all__ = [
    "LoginView",
    "RefreshView",
    "LogoutView",
    "MeView",
    "MeACLView",
    "BootstrapStatusView",
    "BootstrapInitView",
    "BootstrapOrgView",
    "PasswordChangeView",
    "TwoFactorSetupView",
    "TwoFactorConfirmView",
    "TwoFactorVerifyView",
    "TwoFactorDisableView",
]

from django.urls import path

from .views import (
    LegacyBootstrapInitView,
    LegacyBootstrapOrgView,
    LegacyBootstrapStatusView,
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

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("me/acl/", MeACLView.as_view(), name="me-acl"),
    path("password/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("2fa/enable/", TwoFactorSetupView.as_view(), name="auth-2fa-enable"),
    path("2fa/confirm/", TwoFactorConfirmView.as_view(), name="auth-2fa-confirm"),
    path("2fa/verify/", TwoFactorVerifyView.as_view(), name="auth-2fa-verify"),
    path("2fa/disable/", TwoFactorDisableView.as_view(), name="auth-2fa-disable"),
    # Legacy bootstrap wrappers (deprecated, sunset 2026-05-17)
    path("bootstrap/status/", LegacyBootstrapStatusView.as_view(), name="auth-bootstrap-status-legacy"),
    path("bootstrap/init/", LegacyBootstrapInitView.as_view(), name="auth-bootstrap-init-legacy"),
    path("bootstrap/org/", LegacyBootstrapOrgView.as_view(), name="auth-bootstrap-org-legacy"),
]

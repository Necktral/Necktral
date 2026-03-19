from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    MeACLView,
    MeView,
    RefreshView,
    BootstrapStatusView,
    BootstrapInitView,
    BootstrapOrgView,
    PasswordChangeView,
    TwoFactorSetupView,
    TwoFactorConfirmView,
    TwoFactorVerifyView,
    TwoFactorDisableView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("me/acl/", MeACLView.as_view(), name="me-acl"),
    # Onboarding / bootstrap
    path("bootstrap/status/", BootstrapStatusView.as_view(), name="auth-bootstrap-status"),
    path("bootstrap/init/", BootstrapInitView.as_view(), name="auth-bootstrap-init"),
    path("bootstrap/org/", BootstrapOrgView.as_view(), name="auth-bootstrap-org"),
    # Password change (forzado)
    path("password/", PasswordChangeView.as_view(), name="auth-password-change"),
    # 2FA (TOTP)
    path("2fa/enable/", TwoFactorSetupView.as_view(), name="auth-2fa-enable"),
    path("2fa/confirm/", TwoFactorConfirmView.as_view(), name="auth-2fa-confirm"),
    path("2fa/verify/", TwoFactorVerifyView.as_view(), name="auth-2fa-verify"),
    path("2fa/disable/", TwoFactorDisableView.as_view(), name="auth-2fa-disable"),
]

from __future__ import annotations

import os

import pyotp
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    # Use AbstractBaseUser or the specific User model for typing
    UserType = AbstractBaseUser
else:
    UserType = Any

User = get_user_model()


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


class Command(BaseCommand):
    help = "Seed usuarios para simulacion de auth (k6)."

    def add_arguments(self, parser):
        parser.add_argument("--admin-username", default=os.getenv("AUTH_SIM_ADMIN_USERNAME", "k6_admin"))
        parser.add_argument("--admin-email", default=os.getenv("AUTH_SIM_ADMIN_EMAIL", "k6_admin@test.com"))
        parser.add_argument("--admin-password", default=os.getenv("AUTH_SIM_ADMIN_PASSWORD", "Pass12345__Strong"))
        parser.add_argument("--admin-totp-secret", default=os.getenv("AUTH_SIM_ADMIN_TOTP_SECRET", ""))
        parser.add_argument("--admin-enable-2fa", action="store_true", default=_truthy(os.getenv("AUTH_SIM_ADMIN_2FA", "1")))
        parser.add_argument("--admin-superuser", action="store_true", default=_truthy(os.getenv("AUTH_SIM_ADMIN_SUPERUSER", "0")))

        parser.add_argument("--user-username", default=os.getenv("AUTH_SIM_USER_USERNAME", "k6_user"))
        parser.add_argument("--user-email", default=os.getenv("AUTH_SIM_USER_EMAIL", "k6_user@test.com"))
        parser.add_argument("--user-password", default=os.getenv("AUTH_SIM_USER_PASSWORD", "Pass12345__Strong"))
        parser.add_argument("--show-secrets", action="store_true", default=_truthy(os.getenv("AUTH_SIM_SHOW_SECRETS", "0")))

    def _upsert_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        is_staff: bool,
        is_superuser: bool,
        enable_2fa: bool,
        totp_secret: str,
    ) -> tuple[UserType, str]:
        user = User.objects.filter(username=username).first()
        created = False
        if not user:
            user = User.objects.create_user(
                username=username,
                email=email or None,
                password=password,
            )
            created = True
        else:
            if email:
                user.email = email
            user.set_password(password)

        user.is_active = True
        user.is_staff = bool(is_staff)
        user.is_superuser = bool(is_superuser)
        if hasattr(user, "must_change_password"):
            user.must_change_password = False
        if hasattr(user, "is_setup_complete"):
            user.is_setup_complete = True

        if enable_2fa:
            if not totp_secret:
                totp_secret = user.totp_secret or pyotp.random_base32()
            user.totp_secret = totp_secret
            user.totp_enabled = True
            user.totp_confirmed_at = timezone.now()
        else:
            user.totp_enabled = False
            user.totp_confirmed_at = None
            user.totp_secret = ""

        user.save()
        if created:
            return user, totp_secret
        return user, totp_secret

    def handle(self, *args, **options):
        admin_user, admin_secret = self._upsert_user(
            username=options["admin_username"],
            email=options["admin_email"],
            password=options["admin_password"],
            is_staff=True,
            is_superuser=bool(options["admin_superuser"]),
            enable_2fa=bool(options["admin_enable_2fa"]),
            totp_secret=(options["admin_totp_secret"] or ""),
        )

        regular_user, _ = self._upsert_user(
            username=options["user_username"],
            email=options["user_email"],
            password=options["user_password"],
            is_staff=False,
            is_superuser=False,
            enable_2fa=False,
            totp_secret="",
        )

        self.stdout.write(self.style.SUCCESS("Usuarios de simulacion listos"))
        self.stdout.write(f"ADMIN: {admin_user.username} (staff={admin_user.is_staff}, superuser={admin_user.is_superuser})")
        self.stdout.write(f"USER:  {regular_user.username}")
        if options["show_secrets"] and options["admin_enable_2fa"]:
            self.stdout.write(f"ADMIN_TOTP_SECRET: {admin_secret}")

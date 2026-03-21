import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

User = get_user_model()


@pytest.mark.django_db
def test_seed_auth_users_admin_2fa_explicit_disable():
    call_command(
        "seed_auth_users",
        admin_username="seed_admin_a",
        admin_email="seed_admin_a@test.com",
        user_username="seed_user_a",
        user_email="seed_user_a@test.com",
        admin_2fa="0",
    )

    admin = User.objects.get(username="seed_admin_a")
    assert admin.totp_enabled is False
    assert admin.totp_secret == ""


@pytest.mark.django_db
def test_seed_auth_users_admin_2fa_explicit_override_legacy_flag():
    call_command(
        "seed_auth_users",
        admin_username="seed_admin_b",
        admin_email="seed_admin_b@test.com",
        user_username="seed_user_b",
        user_email="seed_user_b@test.com",
        admin_2fa="0",
        admin_enable_2fa=True,
    )

    admin = User.objects.get(username="seed_admin_b")
    assert admin.totp_enabled is False


@pytest.mark.django_db
def test_seed_auth_users_legacy_flag_still_supported():
    call_command(
        "seed_auth_users",
        admin_username="seed_admin_c",
        admin_email="seed_admin_c@test.com",
        user_username="seed_user_c",
        user_email="seed_user_c@test.com",
        admin_enable_2fa=True,
    )

    admin = User.objects.get(username="seed_admin_c")
    assert admin.totp_enabled is True
    assert isinstance(admin.totp_secret, str)
    assert len(admin.totp_secret) > 0

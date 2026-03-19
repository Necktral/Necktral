from apps.modulos.accounts.models import User
from apps.modulos.iam.bootstrap import create_initial_admin
from apps.modulos.iam.models import OrgUnit


def get_bootstrap_status() -> dict[str, bool]:
    has_user = User.objects.exists()
    has_holding = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING, is_active=True).exists()
    has_company = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, is_active=True).exists()
    setup_required = (not has_holding) or (not has_company)
    return {
        "is_fresh": not has_user,
        "setup_required": bool(setup_required),
    }


def bootstrap_init_admin(data: dict) -> User:
    return create_initial_admin(
        {
            "username": str(data["username"]).strip(),
            "email": str(data.get("email") or ""),
            "password": str(data["password"]),
            "first_name": str(data.get("first_name") or ""),
            "last_name": str(data.get("last_name") or ""),
        }
    )

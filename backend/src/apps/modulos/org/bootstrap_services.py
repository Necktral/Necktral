from apps.modulos.iam.bootstrap import bootstrap_organization


def bootstrap_organization_for_user(user, data: dict) -> dict[str, int]:
    orgs = bootstrap_organization(
        user=user,
        data={
            "holding_name": str(data["holding_name"]).strip(),
            "company_name": str(data["company_name"]).strip(),
            "company_tax_id": str(data.get("company_tax_id") or "").strip(),
            "branch_name": str(data["branch_name"]).strip(),
            "branch_address": str(data.get("branch_address") or "").strip(),
        },
    )
    return {
        "holding_id": orgs["holding"].id,
        "company_id": orgs["company"].id,
        "branch_id": orgs["branch"].id,
    }

import pytest
from django.core.exceptions import ValidationError

from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party, PartyRole


def _org_tree(*, suffix: str = ""):
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding{suffix}",
        code=f"H{suffix}",
        is_active=True,
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company{suffix}",
        code=f"C{suffix}",
        is_active=True,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch{suffix}",
        code=f"B{suffix}",
        is_active=True,
    )
    return holding, company, branch


@pytest.mark.django_db
@pytest.mark.parametrize(
    "party_type",
    [Party.PartyType.NATURAL, Party.PartyType.JURIDICAL, Party.PartyType.INTERNAL],
)
def test_party_can_create_supported_party_types_and_normalizes_fields(party_type):
    _holding, company, _branch = _org_tree(suffix=party_type)

    party = Party.objects.create(
        company=company,
        party_type=party_type,
        display_name="  Cliente Demo  ",
        legal_name="  Cliente Demo SA  ",
        tax_id=" ruc-001 ",
        national_id=" ced-001 ",
        email=" CLIENTE@EXAMPLE.COM ",
        phone=" 8888-0000 ",
    )

    assert party.party_type == party_type
    assert party.display_name == "Cliente Demo"
    assert party.legal_name == "Cliente Demo SA"
    assert party.tax_id == "RUC-001"
    assert party.national_id == "CED-001"
    assert party.email == "cliente@example.com"
    assert party.phone == "8888-0000"
    assert party.status == Party.Status.ACTIVE


@pytest.mark.django_db
def test_party_rejects_tax_id_duplicate_inside_same_company_when_present():
    _holding, company, _branch = _org_tree()
    Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name="Proveedor 1",
        tax_id="ruc-001",
    )

    with pytest.raises(ValidationError):
        Party.objects.create(
            company=company,
            party_type=Party.PartyType.JURIDICAL,
            display_name="Proveedor 2",
            tax_id=" RUC-001 ",
        )


@pytest.mark.django_db
def test_party_rejects_national_id_duplicate_inside_same_company_when_present():
    _holding, company, _branch = _org_tree()
    Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name="Persona 1",
        national_id="ced-001",
    )

    with pytest.raises(ValidationError):
        Party.objects.create(
            company=company,
            party_type=Party.PartyType.NATURAL,
            display_name="Persona 2",
            national_id=" CED-001 ",
        )


@pytest.mark.django_db
def test_party_allows_same_identifiers_in_different_companies():
    holding, company_a, _branch_a = _org_tree(suffix="A")
    company_b = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name="CompanyB",
        code="CB",
        is_active=True,
    )

    Party.objects.create(
        company=company_a,
        party_type=Party.PartyType.NATURAL,
        display_name="Persona A",
        tax_id="RUC-001",
        national_id="CED-001",
    )
    party_b = Party.objects.create(
        company=company_b,
        party_type=Party.PartyType.NATURAL,
        display_name="Persona B",
        tax_id="RUC-001",
        national_id="CED-001",
    )

    assert party_b.tax_id == "RUC-001"
    assert party_b.national_id == "CED-001"


@pytest.mark.django_db
def test_party_rejects_holding_or_branch_as_company_scope():
    holding, company, branch = _org_tree()

    with pytest.raises(ValidationError):
        Party.objects.create(
            company=holding,
            party_type=Party.PartyType.INTERNAL,
            display_name="Holding no permitido",
        )

    with pytest.raises(ValidationError):
        Party.objects.create(
            company=branch,
            party_type=Party.PartyType.INTERNAL,
            display_name="Branch no permitido",
        )

    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.INTERNAL,
        display_name="Company permitida",
    )
    assert party.company == company


@pytest.mark.django_db
def test_party_roles_allow_multiple_business_roles_and_reject_duplicate_active_role():
    _holding, company, _branch = _org_tree()
    party = Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name="Contraparte Multirol",
    )

    customer_role = PartyRole.objects.create(party=party, role=PartyRole.Role.CUSTOMER)
    supplier_role = PartyRole.objects.create(party=party, role=PartyRole.Role.SUPPLIER)

    assert customer_role.is_active is True
    assert supplier_role.is_active is True
    assert party.roles.filter(is_active=True).count() == 2

    with pytest.raises(ValidationError):
        PartyRole.objects.create(party=party, role=PartyRole.Role.CUSTOMER)

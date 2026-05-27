# HR Party Link Integration (PR93)

## Context

PR93 introduces a link between HR Employee records and Parties so access lifecycle actions can operate on a canonical party identity.

## Scope

- Add `Employee.party` relation and migration.
- Extend HR services/views/serializers for assignment and revocation flows.
- Add tests for party-link behavior and role lifecycle automation.
- Ratchet architecture dependency baseline for `modulos.hr->modulos.parties`.

## Blast Radius

- Domains touched: `modulos.hr`, `modulos.audit`.
- Layer mix includes runtime backend plus migration.
- Classified by guard as high risk due to migration plus runtime changes.

## Controls

- Keep change set limited to HR party link behavior and required contracts.
- Enforce architecture dependency ratchet explicitly in baseline.
- Keep PR in draft until blocking checks are green.

## Validation

- `python manage.py check`
- `python manage.py migrate --plan`
- `python manage.py makemigrations hr --check --dry-run`
- `make backend-pytest PYTEST_ARGS="-q src/tests/test_parties_models.py src/tests/test_parties_services.py src/tests/test_hr_party_link.py src/tests/test_hr_position_role_automation.py src/tests/test_hr_revoke_access_endpoint.py src/tests/test_hr_end_assignment_endpoint.py"`
- `make backend-pytest PYTEST_ARGS="-q tests/test_audit_chain_integrity.py"`

## Rollback

- Revert PR93 merge commit.
- Drop migration `hr.0005_employee_party` only via follow-up controlled migration if already applied in shared environments.

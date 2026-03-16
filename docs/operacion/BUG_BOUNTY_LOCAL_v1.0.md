# Bug Bounty Local (Sin Sync Remoto)

Versión: v1.0  
Fecha: 2026-03-09  
Estado: **Operativo**

## Objetivo

Ejecutar un bug bounty reproducible sobre el repositorio local completo, generando evidencia versionada y gate final `PASS/FAIL`.

## Comando canónico

Desde la raíz del repo:

```bash
./qa/run_bug_bounty_local.sh
```

Opcional con timestamp fijo:

```bash
./qa/run_bug_bounty_local.sh 20260309_1200
```

## Salida esperada

Se crea `docs/operacion/evidencia/bug_bounty_local_<timestamp>/` con:

- `00_baseline.txt`
- `10_gitleaks.json`
- `11_pip_audit.json`
- `12_npm_audit.json`
- `13_trivy_fs.json`
- `14_static_scan.txt`
- `23_dast_zap.json` (si `BUG_BOUNTY_DAST_URL` está definido)
- `23_dast_zap.md` (si `BUG_BOUNTY_DAST_URL` está definido)
- `20_django_check.txt`
- `21_audit_integrity.json`
- `22_security_pytest.txt`
- `30_bug_bounty_summary.json`
- `31_bug_bounty_findings.md`
- `32_bug_bounty_manifest_hash.txt`

## Gate de aceptación

`PASS` solo si:

- `gitleaks_clean=true`
- `pip_audit_blocking_clean=true` (sin HIGH/CRITICAL con fix disponible)
- `npm_audit_blocking_clean=true` (sin HIGH/CRITICAL con fix disponible)
- `static_scan_pass=true`
- `dast_pass=true` (obligatorio solo cuando `BUG_BOUNTY_REQUIRE_DAST=1`)
- `manage_check_pass=true`
- `audit_chain_pass=true`
- `security_pytest_pass=true`

## DAST opcional

Para activar DAST con ZAP baseline:

```bash
BUG_BOUNTY_DAST_URL=http://localhost:8000 \
BUG_BOUNTY_REQUIRE_DAST=1 \
./qa/run_bug_bounty_local.sh
```

## Notas de gobernanza

- El escaneo usa `.gitleaks.toml` del repo.
- `backend/**` (legado) y `docs/operacion/evidencia/**` se excluyen en gitleaks por política activa.
- Este flujo no hace `git pull/fetch` ni sincronización remota.

.PHONY: qa-backend-gunicorn qa-backend-gunicorn-performance qa-backend-runserver \
	qa-load-user qa-load-reset-axes qa-load-smoke qa-load-stress qa-gate3 qa-gate3-security qa-gate3-performance qa-gate3-run \
	qa-branch-hygiene qa-branch-hygiene-cleanup-plan qa-branch-hygiene-cleanup \
	qa-operational-hygiene qa-operational-gate qa-operational-pilot-stage1 qa-operational-pilot-stage2 qa-operational-pilot-stage3 qa-operational-pilot-rollback qa-operational-all \
	qa-operational-go-live \
	qa-ci-up qa-ci-fresh qa-ci-ci qa-backend-wait qa-ci-gate1 qa-ci-gate2 qa-ci-gate3 qa-ci \
	qa-backend-bandit qa-backend-ruff qa-backend-mypy qa-verify-static-gate qa-reporting-registry-guard qa-reporting-registry-guard-host qa-reporting-contract-version-guard qa-reporting-contract-version-guard-host qa-pythonpath-bootstrap-guard qa-makemigrations-check qa-backend-mypy-baseline-refresh qa-backend-tests qa-static-scan qa-namespace-guard qa-analytics-contract-guard qa-frontend-ci qa-audit-integrity qa-reporting-r8-gate qa-verify-reporting-r8-gate-artifact \
	docker-clean docker-clean-all

BASE_URL ?= http://localhost:8000/api
K6_IMAGE ?= grafana/k6

QA_REPORTS_DIR ?= qa/reports
QA_KEEP_FRONTEND ?= 1
QA_PYTEST_DB_SLOT ?=
QA_PYTEST_DB_BASE_NAME ?= test_erp_db
REPORTING_R8_GATE_WARN_UNTIL ?= 2026-04-07
REPORTING_R8_GATE_HARD_FAIL_FROM ?= 2026-04-08
REPORTING_R8_GATE_WINDOW_HOURS ?= 24
REPORTING_R8_GATE_SNAPSHOT_P95_MAX_MS ?= 800
REPORTING_R8_GATE_NEAR_RT_P95_MAX_MS ?= 1500
REPORTING_R8_GATE_ERROR_RATE_MAX_PCT ?= 0.5
QA_MYPY_STRICT_TARGETS ?= \
	backend/src/apps/kernels/accounting \
	backend/src/tests/test_phase3_cec_execute_api.py \
	backend/src/tests/test_phase5_accounting_api.py \
	backend/src/tests/test_phase6_adapter_b_readiness.py \
	backend/src/tests/test_phase7b_intercompany_consolidation.py \
	backend/src/tests/test_phase10_procurement_4b.py \
	backend/src/tests/test_phase11_intercompany_advanced.py

# Si QA_FRESH_DB=1, destruye volúmenes (DB limpia) antes de levantar.
# Útil para CI determinista o cuando hay datos locales viejos que rompen Gate 3.
QA_FRESH_DB ?= 0

# Credenciales por defecto (ajusta en tu entorno/CI)
USERNAME ?= k6
PASSWORD ?=
LOGIN_CHURN_USERNAME ?= k6_churn
LOGIN_CHURN_PASSWORD ?= $(PASSWORD)

# k6 defaults
VUS ?= 5
DURATION ?= 30s

# Gate 3 defaults (overrideables)
# Modelo dual:
# - security: perfil estable para CI/PR (respeta anti-abuso real y evita falsos fallos).
# - performance: perfil extendido para capacidad (usa backend con throttles/axes amplios).
STRESS_WARMUP ?= 15s
STRESS_SUSTAIN ?= 60s
STRESS_COOLDOWN ?= 15s
STRESS_VUS_WARMUP ?= 10
STRESS_VUS_TARGET ?= 50
STRESS_LOGIN_RATE_START ?= 1
STRESS_LOGIN_RATE_WARMUP ?= 2
STRESS_LOGIN_RATE_TARGET ?= 5
STRESS_SLEEP ?= 0.1
SMOKE_SLEEP ?= 1.0
SMOKE_VUS ?= 2
SMOKE_DURATION ?= 5s
LOGIN_CHURN_ENABLED ?= 1
QA_LOAD_PROFILE ?= security

# Overrides de performance profile (se aplican en qa-backend-gunicorn-performance).
DRF_THROTTLE_AUTH_LOGIN_PERF ?= 1200/min
DRF_THROTTLE_USER_PERF ?= 12000/min
DRF_THROTTLE_ME_READ_PERF ?= 12000/min
DRF_THROTTLE_ME_ACL_READ_PERF ?= 12000/min
AXES_FAILURE_LIMIT_PERF ?= 10000
AXES_COOLOFF_TIME_PERF ?= 1

# Operacional Billing/Inventory/Accounting (Fase 4/Fase 5)
OPER_BILLING_VUS ?= 6
OPER_INVENTORY_VUS ?= 6
OPER_POSTING_VUS ?= 1
OPER_DURATION ?= 2m

qa-load-reset-axes:
	docker compose exec -T backend python manage.py axes_reset

qa-backend-gunicorn:
	USE_GUNICORN=1 \
	GUNICORN_THREADS=4 \
	GUNICORN_KEEPALIVE=10 \
	docker compose up -d --build --force-recreate backend

qa-backend-gunicorn-performance:
	USE_GUNICORN=1 \
	GUNICORN_THREADS=4 \
	GUNICORN_KEEPALIVE=10 \
	DRF_THROTTLE_AUTH_LOGIN="$(DRF_THROTTLE_AUTH_LOGIN_PERF)" \
	DRF_THROTTLE_USER="$(DRF_THROTTLE_USER_PERF)" \
	DRF_THROTTLE_ME_READ="$(DRF_THROTTLE_ME_READ_PERF)" \
	DRF_THROTTLE_ME_ACL_READ="$(DRF_THROTTLE_ME_ACL_READ_PERF)" \
	AXES_FAILURE_LIMIT="$(AXES_FAILURE_LIMIT_PERF)" \
	AXES_COOLOFF_SECONDS="$(AXES_COOLOFF_TIME_PERF)" \
	docker compose up -d --build --force-recreate backend

qa-backend-runserver:
	USE_GUNICORN=0 docker compose up -d --build --force-recreate backend

# --- QA Runner (Gates 1–3) ---

qa-ci-up:
	@if [ "$(QA_FRESH_DB)" = "1" ]; then \
		echo "[qa] QA_FRESH_DB=1: bajando stack y volúmenes..."; \
		docker compose down -v --remove-orphans; \
	fi
	docker compose up -d --build db backend
	$(MAKE) qa-backend-wait

qa-backend-wait:
	docker compose exec -T backend bash -lc "python /app/qa/wait_backend_ready.py"

qa-ci-fresh:
	$(MAKE) QA_FRESH_DB=1 qa-ci

# Alias explícito para pipelines CI
qa-ci-ci: qa-ci-fresh

qa-static-scan:
	docker compose exec -T backend bash -lc "chmod +x /app/qa/static_scan_backend.sh && /app/qa/static_scan_backend.sh /app"

qa-namespace-guard:
	python3 qa/namespace_layout_guard.py --root .

qa-analytics-contract-guard:
	python3 qa/analytics_contract_guard.py --root .

qa-reporting-registry-guard:
	docker compose exec -T backend bash -lc "python /app/qa/reporting_registry_contract_guard.py --root /app --mode auto"

qa-reporting-registry-guard-host:
	python3 qa/reporting_registry_contract_guard.py --root . --mode ast

qa-reporting-contract-version-guard:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && python /app/qa/reporting_contract_version_guard.py --root /app --baseline qa/contracts/reporting_dataset_contract_baseline.json --output /app/$(QA_REPORTS_DIR)/reporting_contract_guard.json"

qa-reporting-contract-version-guard-host:
	python3 qa/reporting_contract_version_guard.py --root . --baseline qa/contracts/reporting_dataset_contract_baseline.json --output "$(QA_REPORTS_DIR)/reporting_contract_guard.json"

qa-pythonpath-bootstrap-guard:
	python3 qa/pythonpath_bootstrap_guard.py --root .

qa-backend-bandit:
	docker compose exec -T backend bash -lc 'set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && APPS_ROOT=""; for p in /app/backend/src/apps /app/src/apps /app/login_module/src/apps; do [ -d "$$p" ] && APPS_ROOT="$$p" && break; done; [ -n "$$APPS_ROOT" ] || { echo "apps root not found under /app" >&2; exit 2; }; EXCLUDES=$$(find "$$APPS_ROOT/modulos" -mindepth 2 -maxdepth 2 -type d -name migrations 2>/dev/null | tr "\n" "," | sed "s/,$$//"); bandit -q -r "$$APPS_ROOT" -x "$$EXCLUDES" -ll -ii -f txt | tee /app/$(QA_REPORTS_DIR)/bandit.txt'

qa-backend-ruff:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && ruff check /app/backend/src | tee /app/$(QA_REPORTS_DIR)/ruff.txt"

qa-backend-mypy:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && cd /app && mypy --config-file mypy.ini backend/src | tee /app/$(QA_REPORTS_DIR)/mypy.txt"

qa-verify-static-gate:
	python3 qa/verify_static_gate_reports.py --reports-dir "$(QA_REPORTS_DIR)"

qa-makemigrations-check:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/backend && python manage.py makemigrations --check --dry-run --noinput | tee /app/$(QA_REPORTS_DIR)/makemigrations_check.txt"

qa-backend-tests:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/backend && export DJANGO_SETTINGS_MODULE=config.settings.test PYTEST_DB_SLOT='$(QA_PYTEST_DB_SLOT)' PYTEST_DB_BASE_NAME='$(QA_PYTEST_DB_BASE_NAME)'; echo \"[qa] pytest test_db_slot=\$${PYTEST_DB_SLOT:-<auto>} test_db_base=\$${PYTEST_DB_BASE_NAME}\"; coverage run --rcfile /app/backend/.coveragerc -m pytest --junitxml=/app/$(QA_REPORTS_DIR)/pytest.xml && coverage xml --rcfile /app/backend/.coveragerc -o /app/$(QA_REPORTS_DIR)/coverage.xml && coverage report --rcfile /app/backend/.coveragerc | tee /app/$(QA_REPORTS_DIR)/coverage.txt"

qa-audit-integrity:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/backend && python manage.py audit_verify_chain --seed-minimal --format json --output /app/$(QA_REPORTS_DIR)/audit_integrity.json"

qa-reporting-r8-gate:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/backend && python manage.py export_reporting_observability_snapshot --window-hours $(REPORTING_R8_GATE_WINDOW_HOURS) --output /app/$(QA_REPORTS_DIR)/reporting_observability_snapshot.json && python manage.py reporting_r8_gate --window-hours $(REPORTING_R8_GATE_WINDOW_HOURS) --warn-until $(REPORTING_R8_GATE_WARN_UNTIL) --hard-fail-from $(REPORTING_R8_GATE_HARD_FAIL_FROM) --snapshot-p95-max-ms $(REPORTING_R8_GATE_SNAPSHOT_P95_MAX_MS) --near-realtime-p95-max-ms $(REPORTING_R8_GATE_NEAR_RT_P95_MAX_MS) --error-rate-max-pct $(REPORTING_R8_GATE_ERROR_RATE_MAX_PCT) --output /app/$(QA_REPORTS_DIR)/reporting_r8_gate.json"

qa-verify-reporting-r8-gate-artifact:
	python3 qa/verify_reporting_r8_gate_artifact.py --artifact "$(QA_REPORTS_DIR)/reporting_r8_gate.json" --output "$(QA_REPORTS_DIR)/reporting_r8_gate_guard.json"

qa-frontend-ci:
	docker compose --profile qa run --rm frontend_ci

# Gate 1: calidad estática + typecheck
qa-ci-gate1: qa-ci-up qa-namespace-guard qa-analytics-contract-guard qa-reporting-registry-guard qa-reporting-contract-version-guard qa-pythonpath-bootstrap-guard qa-static-scan qa-backend-bandit qa-backend-ruff qa-backend-mypy qa-verify-static-gate qa-makemigrations-check qa-frontend-ci

# Gate 2: pruebas deterministas (pytest + cobertura)
qa-ci-gate2: qa-ci-up qa-backend-tests

# Gate 3: integridad de auditoría (reporte)
qa-ci-gate3: qa-ci-up qa-audit-integrity qa-reporting-r8-gate qa-verify-reporting-r8-gate-artifact

# Runner completo Gates 1–3
qa-ci:
	QA_REPORTS_DIR="$(QA_REPORTS_DIR)" QA_FRESH_DB="$(QA_FRESH_DB)" QA_KEEP_FRONTEND="$(QA_KEEP_FRONTEND)" bash ./qa/run_qa_ci.sh

# --- Docker helpers (dev/local) ---

# Limpia contenedores huérfanos sin tocar volúmenes. Útil cuando ves “copias”.
docker-clean:
	@echo "[docker] down --remove-orphans (sin volúmenes)…"
	@docker compose down --remove-orphans || true
	@echo "[docker] removiendo contenedores EXITED con imagen erp_crm-backend…"
	@docker rm -f $$(docker ps -aq --filter status=exited --filter ancestor=erp_crm-backend:latest) 2>/dev/null || true
	@echo "[docker] listo. Contenedores actuales:"
	@docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'

# Variante agresiva: también elimina volúmenes (pierdes DB local).
docker-clean-all:
	@echo "[docker] down -v --remove-orphans (ELIMINA volúmenes)…"
	@docker compose down -v --remove-orphans || true
	@$(MAKE) docker-clean

qa-load-user:
	@if [ -z "$(PASSWORD)" ]; then echo "Set PASSWORD before running qa-load-user"; exit 1; fi
	# Se crean 2 usuarios para evitar colisiones de sesión en cookie mode:
	# - USERNAME: flujo principal me/acl
	# - LOGIN_CHURN_USERNAME: churn de login para stress
	docker compose exec -T backend python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); users=((\"$(USERNAME)\",\"$(PASSWORD)\",\"k6@test.com\"),(\"$(LOGIN_CHURN_USERNAME)\",\"$(LOGIN_CHURN_PASSWORD)\",\"k6_churn@test.com\")); [((lambda u: (setattr(u,'email',email), setattr(u,'is_staff',True), u.set_password(pwd), setattr(u,'must_change_password',False), u.save()))(User.objects.get_or_create(username=name)[0])) for name,pwd,email in users]; print('K6_USERS_READY')"

qa-load-smoke:
	docker run --rm --network host \
		-v "$(PWD)":/work -w /work \
		-e BASE_URL=$(BASE_URL) \
		-e USERNAME=$(USERNAME) \
		-e PASSWORD=$(PASSWORD) \
		-e QA_LOAD_PROFILE=$(QA_LOAD_PROFILE) \
		-e SLEEP=$(SMOKE_SLEEP) \
		-e VUS=$(VUS) \
		-e DURATION=$(DURATION) \
		$(K6_IMAGE) run qa/k6/auth_smoke.js

# Stress test (stages). Ajusta con variables env si hace falta:
# VUS_WARMUP, VUS_TARGET, WARMUP, SUSTAIN, COOLDOWN, SLEEP
qa-load-stress:
	docker run --rm --network host \
		-v "$(PWD)":/work -w /work \
		-e BASE_URL=$(BASE_URL) \
		-e USERNAME=$(USERNAME) \
		-e PASSWORD=$(PASSWORD) \
		-e LOGIN_CHURN_USERNAME=$(LOGIN_CHURN_USERNAME) \
		-e LOGIN_CHURN_PASSWORD=$(LOGIN_CHURN_PASSWORD) \
		-e QA_LOAD_PROFILE=$(QA_LOAD_PROFILE) \
		-e LOGIN_CHURN_ENABLED=$(LOGIN_CHURN_ENABLED) \
		-e WARMUP=$(STRESS_WARMUP) \
		-e SUSTAIN=$(STRESS_SUSTAIN) \
		-e COOLDOWN=$(STRESS_COOLDOWN) \
		-e VUS_WARMUP=$(STRESS_VUS_WARMUP) \
		-e VUS_TARGET=$(STRESS_VUS_TARGET) \
		-e LOGIN_RATE_START=$(STRESS_LOGIN_RATE_START) \
		-e LOGIN_RATE_WARMUP=$(STRESS_LOGIN_RATE_WARMUP) \
		-e LOGIN_RATE_TARGET=$(STRESS_LOGIN_RATE_TARGET) \
		-e SLEEP=$(STRESS_SLEEP) \
		$(K6_IMAGE) run qa/k6/auth_stress.js

qa-gate3-run:
	@mkdir -p "$(QA_REPORTS_DIR)"
	# Ejecuta smoke + stress, captura logs backend/db y genera resumen JSON determinístico.
	@bash -lc 'set -o pipefail; \
		LOG_FILE="$(QA_REPORTS_DIR)/gate3_$(QA_LOAD_PROFILE).log"; \
		BACKEND_LOG="$(QA_REPORTS_DIR)/backend_gate3_$(QA_LOAD_PROFILE)_tail.log"; \
		DB_LOG="$(QA_REPORTS_DIR)/db_gate3_$(QA_LOAD_PROFILE)_tail.log"; \
		STATUS_FILE="$(QA_REPORTS_DIR)/gate3_$(QA_LOAD_PROFILE)_services_status.txt"; \
		SUMMARY_FILE="$(QA_REPORTS_DIR)/gate3_$(QA_LOAD_PROFILE)_summary.json"; \
		: > "$$LOG_FILE"; \
		rc=0; \
		$(MAKE) qa-load-smoke QA_LOAD_PROFILE=$(QA_LOAD_PROFILE) VUS=$(SMOKE_VUS) DURATION=$(SMOKE_DURATION) SMOKE_SLEEP=$(SMOKE_SLEEP) 2>&1 | tee -a "$$LOG_FILE" || rc=$$?; \
		if [ $$rc -eq 0 ]; then \
			$(MAKE) qa-load-stress QA_LOAD_PROFILE=$(QA_LOAD_PROFILE) LOGIN_CHURN_ENABLED=$(LOGIN_CHURN_ENABLED) 2>&1 | tee -a "$$LOG_FILE" || rc=$$?; \
		fi; \
		docker compose logs --tail=1200 backend > "$$BACKEND_LOG" || true; \
		docker compose logs --tail=800 db > "$$DB_LOG" || true; \
		docker compose ps > "$$STATUS_FILE" || true; \
		python3 qa/gate3_summary.py \
			--profile "$(QA_LOAD_PROFILE)" \
			--exit-code "$$rc" \
			--log "$$LOG_FILE" \
			--backend-log "$$BACKEND_LOG" \
			--output "$$SUMMARY_FILE"; \
		echo "[qa] gate3 profile=$(QA_LOAD_PROFILE) exit_code=$$rc summary=$$SUMMARY_FILE"; \
		exit $$rc'

qa-gate3-security:
	# Perfil canónico de CI: minimiza churn de login y valida estabilidad auth/ACL bajo límites reales.
	$(MAKE) qa-backend-gunicorn
	$(MAKE) qa-load-user
	$(MAKE) qa-load-reset-axes
	$(MAKE) qa-gate3-run QA_LOAD_PROFILE=security LOGIN_CHURN_ENABLED=0 SMOKE_VUS=1 SMOKE_DURATION=3s SMOKE_SLEEP=1.2 STRESS_SLEEP=2.4 STRESS_VUS_WARMUP=1 STRESS_VUS_TARGET=1 STRESS_LOGIN_RATE_START=0 STRESS_LOGIN_RATE_WARMUP=0 STRESS_LOGIN_RATE_TARGET=0

qa-gate3-performance:
	# Perfil de capacidad: habilita churn + mayor concurrencia con backend en modo performance.
	$(MAKE) qa-backend-gunicorn-performance
	$(MAKE) qa-load-user
	$(MAKE) qa-load-reset-axes
	$(MAKE) qa-gate3-run QA_LOAD_PROFILE=performance LOGIN_CHURN_ENABLED=1 STRESS_WARMUP=30s STRESS_SUSTAIN=180s STRESS_COOLDOWN=30s STRESS_VUS_WARMUP=3 STRESS_VUS_TARGET=8 STRESS_SLEEP=0.2 STRESS_LOGIN_RATE_START=1 STRESS_LOGIN_RATE_WARMUP=2 STRESS_LOGIN_RATE_TARGET=3

# Gate 3 canónico para CI: perfil de seguridad.
qa-gate3: qa-gate3-security

qa-branch-hygiene:
	python3 qa/branch_hygiene_report.py \
		--ttl-days 14 \
		--keep "master,main" \
		--output qa/reports/branch_hygiene_report.md \
		--json-output qa/reports/branch_hygiene_report.json

qa-branch-hygiene-cleanup-plan:
	python3 qa/branch_hygiene_cleanup.py \
		--ttl-days 14 \
		--keep "master,main" \
		--output qa/reports/branch_hygiene_cleanup.md \
		--json-output qa/reports/branch_hygiene_cleanup.json

qa-branch-hygiene-cleanup:
	@if [ "$(APPLY)" != "1" ]; then \
		echo "Refusing destructive cleanup without APPLY=1"; \
		echo "Use: make qa-branch-hygiene-cleanup APPLY=1"; \
		exit 1; \
	fi
	python3 qa/branch_hygiene_cleanup.py \
		--ttl-days 14 \
		--keep "master,main" \
		--apply \
		--output qa/reports/branch_hygiene_cleanup.md \
		--json-output qa/reports/branch_hygiene_cleanup.json

qa-operational-hygiene:
	./qa/run_operational_hygiene_checks.sh

qa-operational-gate:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ] || [ -z "$(PASSWORD)" ]; then \
		echo "Set COMPANY_ID, BRANCH_ID y PASSWORD antes de qa-operational-gate"; \
		exit 1; \
	fi
	BASE_URL=$(BASE_URL) \
	COMPANY_ID=$(COMPANY_ID) \
	BRANCH_ID=$(BRANCH_ID) \
	USERNAME=$(USERNAME) \
	PASSWORD=$(PASSWORD) \
	DURATION=$(OPER_DURATION) \
	BILLING_VUS=$(OPER_BILLING_VUS) \
	INVENTORY_VUS=$(OPER_INVENTORY_VUS) \
	POSTING_VUS=$(OPER_POSTING_VUS) \
	./qa/run_operational_performance_gate.sh

qa-operational-pilot-stage1:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ]; then \
		echo "Set COMPANY_ID y BRANCH_ID antes de qa-operational-pilot-stage1"; \
		exit 1; \
	fi
	COMPANY_ID=$(COMPANY_ID) BRANCH_ID=$(BRANCH_ID) ./qa/run_operational_pilot_rollout.sh stage1

qa-operational-pilot-stage2:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ]; then \
		echo "Set COMPANY_ID y BRANCH_ID antes de qa-operational-pilot-stage2"; \
		exit 1; \
	fi
	COMPANY_ID=$(COMPANY_ID) BRANCH_ID=$(BRANCH_ID) ./qa/run_operational_pilot_rollout.sh stage2

qa-operational-pilot-stage3:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ]; then \
		echo "Set COMPANY_ID y BRANCH_ID antes de qa-operational-pilot-stage3"; \
		exit 1; \
	fi
	COMPANY_ID=$(COMPANY_ID) BRANCH_ID=$(BRANCH_ID) ATTEMPT_CLOSE=1 ./qa/run_operational_pilot_rollout.sh stage3

qa-operational-pilot-rollback:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ]; then \
		echo "Set COMPANY_ID y BRANCH_ID antes de qa-operational-pilot-rollback"; \
		exit 1; \
	fi
	COMPANY_ID=$(COMPANY_ID) BRANCH_ID=$(BRANCH_ID) ./qa/run_operational_pilot_rollout.sh rollback

qa-operational-all: qa-operational-hygiene qa-operational-gate qa-operational-pilot-stage1 qa-operational-pilot-stage2 qa-operational-pilot-stage3

qa-operational-go-live:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ] || [ -z "$(PASSWORD)" ]; then \
		echo "Set COMPANY_ID, BRANCH_ID y PASSWORD antes de qa-operational-go-live"; \
		exit 1; \
	fi
	BASE_URL=$(BASE_URL) \
	COMPANY_ID=$(COMPANY_ID) \
	BRANCH_ID=$(BRANCH_ID) \
	USERNAME=$(USERNAME) \
	PASSWORD=$(PASSWORD) \
	REQUIRED_DAYS=$${REQUIRED_DAYS:-7} \
	./qa/run_operational_go_live.sh full

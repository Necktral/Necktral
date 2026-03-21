.PHONY: qa-backend-gunicorn qa-backend-runserver \
	qa-load-user qa-load-reset-axes qa-load-smoke qa-load-smoke-cookie qa-load-smoke-header qa-load-stress qa-gate3 \
	qa-operational-hygiene qa-operational-gate qa-operational-projector-drain qa-operational-aggressive-gate qa-operational-pilot-stage1 qa-operational-pilot-stage2 qa-operational-pilot-stage3 qa-operational-pilot-rollback qa-operational-all \
	qa-operational-go-live \
	qa-auth-sync-prepare qa-auth-sync-smoke qa-auth-sync-reset-run \
	qa-ci-up qa-ci-fresh qa-ci-ci qa-backend-wait qa-ci-gate1 qa-ci-gate2 qa-ci-gate3 qa-ci \
	qa-coverage-domains \
	qa-repo-hygiene qa-repo-hygiene-inventory qa-architecture-boundaries qa-simulation-contract-guard qa-accounting-http-contract-guard \
		qa-repo-comment-audit \
		qa-backend-bandit qa-backend-ruff qa-backend-mypy qa-backend-mypy-baseline-refresh qa-backend-tests qa-static-scan qa-frontend-ci qa-audit-integrity qa-reports-contract-check \
		docker-clean docker-clean-all \
		loadtest-precheck-auth loadtest loadtest-150k

BASE_URL ?= http://localhost:8000/api
K6_IMAGE ?= grafana/k6
BACKEND_DIR ?= backend
BACKEND_SRC ?= $(BACKEND_DIR)/src
CONTAINER_BACKEND_DIR ?= /app/$(BACKEND_DIR)

QA_REPORTS_DIR ?= qa/reports
QA_KEEP_FRONTEND ?= 1
QA_DOMAIN_THRESHOLDS ?= sync_engine=98
QA_MYPY_STRICT_TARGETS ?= \
	$(BACKEND_SRC)/apps/modulos/accounting \
	$(BACKEND_SRC)/tests/test_phase3_cec_execute_api.py \
	$(BACKEND_SRC)/tests/test_phase5_accounting_api.py \
	$(BACKEND_SRC)/tests/test_phase6_adapter_b_readiness.py \
	$(BACKEND_SRC)/tests/test_phase7b_intercompany_consolidation.py \
	$(BACKEND_SRC)/tests/test_phase10_procurement_4b.py \
	$(BACKEND_SRC)/tests/test_phase11_intercompany_advanced.py

# Si QA_FRESH_DB=1, destruye volúmenes (DB limpia) antes de levantar.
# Útil para CI determinista o cuando hay datos locales viejos que rompen Gate 3.
QA_FRESH_DB ?= 0

# Credenciales por defecto (ajusta en tu entorno/CI)
USERNAME ?= k6
PASSWORD ?=
AUTH_SYNC_ADMIN_USERNAME ?= k6_admin
AUTH_SYNC_COMPANY_NAME ?= Acme Demo
AUTH_SYNC_COMPANY_CODE ?= ACME
AUTH_SYNC_BRANCH_NAME ?= Central
AUTH_SYNC_BRANCH_CODE ?= CEN

# k6 defaults
VUS ?= 5
DURATION ?= 30s
AUTH_FLOW_MODE ?= auto

# Gate 3 defaults (overrideables)
STRESS_WARMUP ?= 15s
STRESS_SUSTAIN ?= 60s
STRESS_COOLDOWN ?= 15s
STRESS_VUS_WARMUP ?= 10
STRESS_VUS_TARGET ?= 50
STRESS_LOGIN_RATE_START ?= 1
STRESS_LOGIN_RATE_WARMUP ?= 2
STRESS_LOGIN_RATE_TARGET ?= 5
STRESS_SLEEP ?= 0.1

# Operacional Billing/Inventory/Accounting (Fase 4/Fase 5)
OPER_BILLING_VUS ?= 6
OPER_INVENTORY_VUS ?= 6
OPER_POSTING_VUS ?= 1
OPER_DURATION ?= 2m

# Perfil específico para gate operacional (evita heredar por accidente el perfil agresivo de loadtest)
OPER_GATE_BILLING_VUS ?= 1
OPER_GATE_INVENTORY_VUS ?= 1
OPER_GATE_POSTING_VUS ?= 1
OPER_GATE_DURATION ?= 90s
OPER_GATE_SLEEP ?= 0.35
OPER_GATE_POSTING_LIMIT ?= 15
OPER_GATE_AUTH_TRANSPORT ?= header
OPER_AGGR_BILLING_VUS ?= 2
OPER_AGGR_INVENTORY_VUS ?= 2
OPER_AGGR_POSTING_VUS ?= 1
OPER_AGGR_DURATION ?= 2m
OPER_AGGR_SLEEP ?= 0.1
OPER_AGGR_POSTING_LIMIT ?= 15
OPER_AGGR_RUNS ?= 3
LOADTEST_ENV_FILE ?= .env.loadtest
PRECHECK_SIM_PROFILE ?= integral
TARGET_HTTP_REQS ?= 150000
RUN_QA_GATES ?= 1
RUN_SECURITY_SCAN ?= 1
RUN_LOADTEST_PRECHECK ?= 1
REPO_AUDIT_FETCH ?= 1
REPO_AUDIT_TOP_N ?= 20
REPO_AUDIT_MIN_LINES ?= 120

LOADTEST_TOTAL_DURATION_EFFECTIVE = $(if $(filter command% environment%,$(origin TOTAL_DURATION)),$(TOTAL_DURATION),15m)
LOADTEST_AUTH_VUS_EFFECTIVE = $(if $(filter command% environment%,$(origin AUTH_VUS)),$(AUTH_VUS),120)
LOADTEST_AUTH_ADMIN_2FA_VUS_EFFECTIVE = $(if $(filter command% environment%,$(origin AUTH_ADMIN_2FA_VUS)),$(AUTH_ADMIN_2FA_VUS),6)
LOADTEST_AUTH_ADMIN_2FA_SLEEP_EFFECTIVE = $(if $(filter command% environment%,$(origin AUTH_ADMIN_2FA_SLEEP)),$(AUTH_ADMIN_2FA_SLEEP),1)
LOADTEST_OPER_BILLING_VUS_EFFECTIVE = $(if $(filter command% environment%,$(origin OPER_BILLING_VUS)),$(OPER_BILLING_VUS),80)
LOADTEST_OPER_INVENTORY_VUS_EFFECTIVE = $(if $(filter command% environment%,$(origin OPER_INVENTORY_VUS)),$(OPER_INVENTORY_VUS),80)
LOADTEST_OPER_POSTING_VUS_EFFECTIVE = $(if $(filter command% environment%,$(origin OPER_POSTING_VUS)),$(OPER_POSTING_VUS),24)

qa-load-reset-axes:
	docker compose exec -T backend python manage.py axes_reset

qa-backend-gunicorn:
	USE_GUNICORN=1 \
	GUNICORN_THREADS=4 \
	GUNICORN_KEEPALIVE=10 \
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

qa-auth-sync-prepare:
	docker compose exec -T backend bash -lc "python /app/qa/wait_backend_schema_ready.py"
	docker compose exec -T backend python src/manage.py seed_auth_users --admin-2fa 0 --show-secrets
	docker compose exec -T backend python src/manage.py bootstrap_company --no-input --company-name '$(AUTH_SYNC_COMPANY_NAME)' --company-code $(AUTH_SYNC_COMPANY_CODE) --branch-name '$(AUTH_SYNC_BRANCH_NAME)' --branch-code $(AUTH_SYNC_BRANCH_CODE) --admin-username $(AUTH_SYNC_ADMIN_USERNAME)

qa-auth-sync-smoke:
	QA_REPORTS_DIR="$(QA_REPORTS_DIR)" AUTH_SYNC_BASE_URL="$(BASE_URL)/backend" AUTH_SYNC_USERNAME="$(AUTH_SYNC_ADMIN_USERNAME)" bash ./qa/run_auth_sync_smoke.sh

qa-auth-sync-reset-run:
	$(MAKE) QA_FRESH_DB=1 qa-ci-up
	$(MAKE) qa-auth-sync-prepare
	$(MAKE) qa-auth-sync-smoke

# Alias explícito para pipelines CI
qa-ci-ci: qa-ci-fresh

qa-static-scan:
	docker compose exec -T backend bash -lc "chmod +x /app/qa/static_scan_backend.sh && /app/qa/static_scan_backend.sh /app"

qa-backend-bandit:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && bandit -q -r $(CONTAINER_BACKEND_DIR)/src/apps /app/kernels -x $(CONTAINER_BACKEND_DIR)/src/apps/modulos/*/migrations,/app/kernels/*/migrations -ll -ii -f txt | tee /app/$(QA_REPORTS_DIR)/bandit.txt"

qa-backend-ruff:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && ruff check $(CONTAINER_BACKEND_DIR)/src | tee /app/$(QA_REPORTS_DIR)/ruff.txt"

qa-backend-mypy:
	docker compose exec -T backend bash -lc 'set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && cd /app && mypy --no-incremental --config-file mypy.ini $(QA_MYPY_STRICT_TARGETS) | tee /app/$(QA_REPORTS_DIR)/mypy_strict_critical.txt ; strict_status=$${PIPESTATUS[0]} ; mypy --no-incremental --config-file mypy.ini $(BACKEND_SRC) | tee /app/$(QA_REPORTS_DIR)/mypy.txt ; mypy_status=$${PIPESTATUS[0]} ; python /app/qa/mypy_baseline_guard.py check --report /app/$(QA_REPORTS_DIR)/mypy.txt --baseline /app/qa/mypy_baseline.txt --delta-report /app/$(QA_REPORTS_DIR)/mypy_delta.json --delta-text /app/$(QA_REPORTS_DIR)/mypy_delta.txt ; guard_status=$$? ; if [ $$strict_status -ne 0 ]; then echo "[qa] mypy strict critical failed." ; exit $$strict_status ; fi ; if [ $$guard_status -ne 0 ]; then exit $$guard_status ; fi ; if [ $$mypy_status -ne 0 ]; then echo "[qa] mypy baseline active: existing debt tolerada, no nuevos errores." ; fi ; exit 0'

qa-backend-mypy-baseline-refresh:
	docker compose exec -T backend bash -lc "set -o pipefail && cd /app && mypy --config-file mypy.ini $(BACKEND_SRC) | tee /app/qa/reports/mypy.txt ; python /app/qa/mypy_baseline_guard.py refresh --report /app/qa/reports/mypy.txt --baseline /app/qa/mypy_baseline.txt"

qa-backend-tests:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && cd $(CONTAINER_BACKEND_DIR) && coverage run --rcfile $(CONTAINER_BACKEND_DIR)/.coveragerc -m pytest --ds=config.settings.test --junitxml=/app/$(QA_REPORTS_DIR)/pytest.xml && coverage xml --rcfile $(CONTAINER_BACKEND_DIR)/.coveragerc -o /app/$(QA_REPORTS_DIR)/coverage.xml && coverage report --rcfile $(CONTAINER_BACKEND_DIR)/.coveragerc | tee /app/$(QA_REPORTS_DIR)/coverage.txt"

qa-coverage-domains:
	docker compose exec -T backend bash -lc "python /app/qa/coverage_by_domain.py --coverage-xml /app/$(QA_REPORTS_DIR)/coverage.xml --json-output /app/$(QA_REPORTS_DIR)/coverage_by_domain.json --md-output /app/$(QA_REPORTS_DIR)/coverage_by_domain.md $(foreach threshold,$(QA_DOMAIN_THRESHOLDS),--min-domain $(threshold))"

qa-audit-integrity:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd $(CONTAINER_BACKEND_DIR) && python manage.py audit_verify_chain --seed-minimal --format json --output /app/$(QA_REPORTS_DIR)/audit_integrity.json"

qa-reports-contract-check:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd $(CONTAINER_BACKEND_DIR) && python manage.py reports_check_contracts | tee /app/$(QA_REPORTS_DIR)/reports_contract_check.txt && python manage.py reports_verify_reproducibility | tee /app/$(QA_REPORTS_DIR)/reports_repro_check.txt"

qa-frontend-ci:
	docker compose --profile qa run --rm frontend_ci

qa-repo-hygiene:
	python3 ./qa/repo_hygiene_guard.py

qa-architecture-boundaries:
	python3 ./qa/architecture_boundaries_guard.py

qa-simulation-contract-guard:
	python3 ./qa/simulation_contract_guard.py

qa-accounting-http-contract-guard:
	python3 ./qa/accounting_http_contract_guard.py

qa-repo-hygiene-inventory:
	python3 ./qa/repo_hygiene_inventory.py

# Gate 1: calidad estática + typecheck
qa-ci-gate1: qa-repo-hygiene qa-architecture-boundaries qa-simulation-contract-guard qa-accounting-http-contract-guard qa-ci-up qa-static-scan qa-backend-bandit qa-backend-ruff qa-backend-mypy qa-frontend-ci

# Gate 2: pruebas deterministas (pytest + cobertura)
qa-ci-gate2: qa-ci-up qa-backend-tests qa-coverage-domains qa-reports-contract-check

# Gate 3: integridad de auditoría (reporte)
qa-ci-gate3: qa-ci-up qa-audit-integrity

# Runner completo Gates 1–3
qa-ci:
	QA_REPORTS_DIR="$(QA_REPORTS_DIR)" QA_FRESH_DB="$(QA_FRESH_DB)" QA_KEEP_FRONTEND="$(QA_KEEP_FRONTEND)" bash ./qa/run_qa_ci.sh

qa-repo-comment-audit:
	python3 ./qa/repo_comment_audit.py \
		--json-output ./qa/reports/repo_comment_audit.json \
		--md-output ./qa/reports/repo_comment_audit.md \
		--top-n $(REPO_AUDIT_TOP_N) \
		--min-large-lines $(REPO_AUDIT_MIN_LINES) $(if $(filter 1,$(REPO_AUDIT_FETCH)),--fetch,)

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
	docker compose exec -T backend python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); u, _=User.objects.get_or_create(username='k6'); u.email='k6@test.com'; u.is_staff=True; u.set_password('$(PASSWORD)'); setattr(u, 'must_change_password', False); u.save(); print('K6_USER_READY')"

qa-load-smoke:
	docker run --rm -i --network host \
		-e BASE_URL=$(BASE_URL) \
		-e USERNAME=$(USERNAME) \
		-e PASSWORD=$(PASSWORD) \
		-e VUS=$(VUS) \
		-e DURATION=$(DURATION) \
		-e AUTH_FLOW_MODE=$(AUTH_FLOW_MODE) \
		$(K6_IMAGE) run - < qa/k6/auth_smoke.js

qa-load-smoke-cookie:
	$(MAKE) qa-load-smoke AUTH_FLOW_MODE=cookie

qa-load-smoke-header:
	$(MAKE) qa-load-smoke AUTH_FLOW_MODE=header

# Stress test (stages). Ajusta con variables env si hace falta:
# VUS_WARMUP, VUS_TARGET, WARMUP, SUSTAIN, COOLDOWN, SLEEP
qa-load-stress:
	docker run --rm -i --network host \
		-e BASE_URL=$(BASE_URL) \
		-e USERNAME=$(USERNAME) \
		-e PASSWORD=$(PASSWORD) \
		-e AUTH_FLOW_MODE=$(AUTH_FLOW_MODE) \
		-e WARMUP=$(STRESS_WARMUP) \
		-e SUSTAIN=$(STRESS_SUSTAIN) \
		-e COOLDOWN=$(STRESS_COOLDOWN) \
		-e VUS_WARMUP=$(STRESS_VUS_WARMUP) \
		-e VUS_TARGET=$(STRESS_VUS_TARGET) \
		-e LOGIN_RATE_START=$(STRESS_LOGIN_RATE_START) \
		-e LOGIN_RATE_WARMUP=$(STRESS_LOGIN_RATE_WARMUP) \
		-e LOGIN_RATE_TARGET=$(STRESS_LOGIN_RATE_TARGET) \
		-e SLEEP=$(STRESS_SLEEP) \
		$(K6_IMAGE) run - < qa/k6/auth_stress.js

# Gate 3 (determinista): prepara entorno + smoke + stress
qa-gate3:
	$(MAKE) qa-backend-gunicorn
	$(MAKE) qa-load-user
	$(MAKE) qa-load-reset-axes
	$(MAKE) qa-load-smoke VUS=2 DURATION=5s
	$(MAKE) qa-load-stress

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
	DURATION=$(OPER_GATE_DURATION) \
	BILLING_VUS=$(OPER_GATE_BILLING_VUS) \
	INVENTORY_VUS=$(OPER_GATE_INVENTORY_VUS) \
	POSTING_VUS=$(OPER_GATE_POSTING_VUS) \
	SLEEP=$(OPER_GATE_SLEEP) \
	POSTING_LIMIT=$(OPER_GATE_POSTING_LIMIT) \
	AUTH_TRANSPORT=$(OPER_GATE_AUTH_TRANSPORT) \
	./qa/run_operational_performance_gate.sh

qa-operational-projector-drain:
	@if [ -z "$(COMPANY_ID)" ]; then \
		echo "Set COMPANY_ID antes de qa-operational-projector-drain"; \
		exit 1; \
	fi
	docker compose exec -T backend python src/manage.py run_operational_accounting_projector --company-id $(COMPANY_ID) --limit 500

qa-operational-aggressive-gate:
	@if [ -z "$(COMPANY_ID)" ] || [ -z "$(BRANCH_ID)" ] || [ -z "$(PASSWORD)" ]; then \
		echo "Set COMPANY_ID, BRANCH_ID y PASSWORD antes de qa-operational-aggressive-gate"; \
		exit 1; \
	fi
	COMPANY_ID=$(COMPANY_ID) \
	BRANCH_ID=$(BRANCH_ID) \
	USERNAME=$(USERNAME) \
	PASSWORD=$(PASSWORD) \
	OPER_AGGR_RUNS=$(OPER_AGGR_RUNS) \
	OPER_AGGR_DURATION=$(OPER_AGGR_DURATION) \
	OPER_AGGR_BILLING_VUS=$(OPER_AGGR_BILLING_VUS) \
	OPER_AGGR_INVENTORY_VUS=$(OPER_AGGR_INVENTORY_VUS) \
	OPER_AGGR_POSTING_VUS=$(OPER_AGGR_POSTING_VUS) \
	OPER_AGGR_SLEEP=$(OPER_AGGR_SLEEP) \
	OPER_AGGR_POSTING_LIMIT=$(OPER_AGGR_POSTING_LIMIT) \
	OPER_GATE_AUTH_TRANSPORT=$(OPER_GATE_AUTH_TRANSPORT) \
	LOADTEST_ENV_FILE=$(LOADTEST_ENV_FILE) \
	./qa/run_operational_aggressive_gate.sh

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

loadtest:
	@if [ "$(RUN_LOADTEST_PRECHECK)" = "1" ]; then \
		$(MAKE) loadtest-precheck-auth LOADTEST_ENV_FILE="$(LOADTEST_ENV_FILE)"; \
	fi
	LOADTEST_ENV_FILE="$(LOADTEST_ENV_FILE)" \
	TARGET_HTTP_REQS="$(TARGET_HTTP_REQS)" \
	TOTAL_DURATION="$(LOADTEST_TOTAL_DURATION_EFFECTIVE)" \
	AUTH_VUS="$(LOADTEST_AUTH_VUS_EFFECTIVE)" \
	AUTH_ADMIN_2FA_VUS="$(LOADTEST_AUTH_ADMIN_2FA_VUS_EFFECTIVE)" \
	AUTH_ADMIN_2FA_SLEEP="$(LOADTEST_AUTH_ADMIN_2FA_SLEEP_EFFECTIVE)" \
	OPER_BILLING_VUS="$(LOADTEST_OPER_BILLING_VUS_EFFECTIVE)" \
	OPER_INVENTORY_VUS="$(LOADTEST_OPER_INVENTORY_VUS_EFFECTIVE)" \
	OPER_POSTING_VUS="$(LOADTEST_OPER_POSTING_VUS_EFFECTIVE)" \
	RUN_QA_GATES="$(RUN_QA_GATES)" \
	RUN_SECURITY_SCAN="$(RUN_SECURITY_SCAN)" \
	./simulacion/run_advanced_integral.sh

loadtest-precheck-auth:
	LOADTEST_ENV_FILE="$(LOADTEST_ENV_FILE)" SIM_PROFILE="$(PRECHECK_SIM_PROFILE)" ./simulacion/precheck_loadtest_auth.sh

loadtest-150k:
	$(MAKE) loadtest TARGET_HTTP_REQS=150000

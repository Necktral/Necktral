.PHONY: qa-backend-gunicorn qa-backend-runserver \
	qa-load-user qa-load-reset-axes qa-load-smoke qa-load-stress qa-gate3 \
	qa-operational-hygiene qa-operational-gate qa-operational-pilot-stage1 qa-operational-pilot-stage2 qa-operational-pilot-stage3 qa-operational-pilot-rollback qa-operational-all \
	qa-operational-go-live \
	qa-ci-up qa-ci-fresh qa-ci-ci qa-backend-wait qa-ci-gate1 qa-ci-gate2 qa-ci-gate3 qa-ci \
	qa-repo-comment-audit \
	qa-backend-bandit qa-backend-ruff qa-backend-mypy qa-backend-mypy-baseline-refresh qa-backend-tests qa-static-scan qa-frontend-ci qa-audit-integrity \
	docker-clean docker-clean-all

BASE_URL ?= http://localhost:8000/api
K6_IMAGE ?= grafana/k6

QA_REPORTS_DIR ?= qa/reports
QA_KEEP_FRONTEND ?= 1
QA_MYPY_STRICT_TARGETS ?= \
	login_module/src/apps/accounting \
	login_module/src/tests/test_phase3_cec_execute_api.py \
	login_module/src/tests/test_phase5_accounting_api.py \
	login_module/src/tests/test_phase6_adapter_b_readiness.py \
	login_module/src/tests/test_phase7b_intercompany_consolidation.py \
	login_module/src/tests/test_phase10_procurement_4b.py \
	login_module/src/tests/test_phase11_intercompany_advanced.py

# Si QA_FRESH_DB=1, destruye volúmenes (DB limpia) antes de levantar.
# Útil para CI determinista o cuando hay datos locales viejos que rompen Gate 3.
QA_FRESH_DB ?= 0

# Credenciales por defecto (ajusta en tu entorno/CI)
USERNAME ?= k6
PASSWORD ?=

# k6 defaults
VUS ?= 5
DURATION ?= 30s

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
REPO_AUDIT_FETCH ?= 1
REPO_AUDIT_TOP_N ?= 20
REPO_AUDIT_MIN_LINES ?= 120

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

# Alias explícito para pipelines CI
qa-ci-ci: qa-ci-fresh

qa-static-scan:
	docker compose exec -T backend bash -lc "chmod +x /app/qa/static_scan_backend.sh && /app/qa/static_scan_backend.sh /app"

qa-backend-bandit:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && bandit -q -r /app/login_module/src/apps /app/modulos -x /app/login_module/src/apps/*/migrations,/app/modulos/*/migrations -ll -ii -f txt | tee /app/$(QA_REPORTS_DIR)/bandit.txt"

qa-backend-ruff:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && ruff check /app/login_module/src | tee /app/$(QA_REPORTS_DIR)/ruff.txt"

qa-backend-mypy:
	docker compose exec -T backend bash -lc 'set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && cd /app && mypy --config-file mypy.ini $(QA_MYPY_STRICT_TARGETS) | tee /app/$(QA_REPORTS_DIR)/mypy_strict_critical.txt ; strict_status=$${PIPESTATUS[0]} ; mypy --config-file mypy.ini login_module/src | tee /app/$(QA_REPORTS_DIR)/mypy.txt ; mypy_status=$${PIPESTATUS[0]} ; python /app/qa/mypy_baseline_guard.py check --report /app/$(QA_REPORTS_DIR)/mypy.txt --baseline /app/qa/mypy_baseline.txt --delta-report /app/$(QA_REPORTS_DIR)/mypy_delta.json --delta-text /app/$(QA_REPORTS_DIR)/mypy_delta.txt ; guard_status=$$? ; if [ $$strict_status -ne 0 ]; then echo "[qa] mypy strict critical failed." ; exit $$strict_status ; fi ; if [ $$guard_status -ne 0 ]; then exit $$guard_status ; fi ; if [ $$mypy_status -ne 0 ]; then echo "[qa] mypy baseline active: existing debt tolerated, no nuevos errores." ; fi ; exit 0'

qa-backend-mypy-baseline-refresh:
	docker compose exec -T backend bash -lc "set -o pipefail && cd /app && mypy --config-file mypy.ini login_module/src | tee /app/qa/reports/mypy.txt ; python /app/qa/mypy_baseline_guard.py refresh --report /app/qa/reports/mypy.txt --baseline /app/qa/mypy_baseline.txt"

qa-backend-tests:
	docker compose exec -T backend bash -lc "set -o pipefail && mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/login_module && coverage run --rcfile /app/login_module/.coveragerc -m pytest --ds=config.settings.test --junitxml=/app/$(QA_REPORTS_DIR)/pytest.xml && coverage xml --rcfile /app/login_module/.coveragerc -o /app/$(QA_REPORTS_DIR)/coverage.xml && coverage report --rcfile /app/login_module/.coveragerc | tee /app/$(QA_REPORTS_DIR)/coverage.txt"

qa-audit-integrity:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/login_module && python manage.py audit_verify_chain --seed-minimal --format json --output /app/$(QA_REPORTS_DIR)/audit_integrity.json"

qa-frontend-ci:
	docker compose --profile qa run --rm frontend_ci

# Gate 1: calidad estática + typecheck
qa-ci-gate1: qa-ci-up qa-static-scan qa-backend-bandit qa-backend-ruff qa-backend-mypy qa-frontend-ci

# Gate 2: pruebas deterministas (pytest + cobertura)
qa-ci-gate2: qa-ci-up qa-backend-tests

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
		$(K6_IMAGE) run - < qa/k6/auth_smoke.js

# Stress test (stages). Ajusta con variables env si hace falta:
# VUS_WARMUP, VUS_TARGET, WARMUP, SUSTAIN, COOLDOWN, SLEEP
qa-load-stress:
	docker run --rm -i --network host \
		-e BASE_URL=$(BASE_URL) \
		-e USERNAME=$(USERNAME) \
		-e PASSWORD=$(PASSWORD) \
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

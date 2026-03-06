.PHONY: qa-backend-gunicorn qa-backend-runserver \
	qa-load-user qa-load-reset-axes qa-load-smoke qa-load-stress qa-gate3 \
	qa-ci-up qa-ci-up-build qa-ci-fresh qa-ci-ci qa-backend-wait qa-ci-gate1 qa-ci-gate2 qa-ci-gate3 qa-ci \
	qa-backend-ruff qa-backend-mypy qa-backend-tests qa-static-scan qa-frontend-ci qa-audit-integrity \
	qa-rbac-doctor docker-clean docker-clean-all

BASE_URL ?= http://localhost:8000/api
K6_IMAGE ?= grafana/k6

QA_REPORTS_DIR ?= qa/reports

# Si QA_FRESH_DB=1, destruye volúmenes (DB limpia) antes de levantar.
# Útil para CI determinista o cuando hay datos locales viejos que rompen Gate 3.
QA_FRESH_DB ?= 0

# Credenciales por defecto (ajusta en tu entorno/CI)
USERNAME ?= k6
PASSWORD ?= Pass12345__Strong

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
		echo "[qa] QA_FRESH_DB=1: reconstruyendo imágenes para evitar drift local..."; \
		docker compose build backend; \
	fi
	# Modo estable/local: no fuerza rebuild ni recreación de servicios.
	docker compose up -d db backend frontend
	$(MAKE) qa-backend-wait

# Build explícito cuando quieres refrescar imagen backend manualmente.
qa-ci-up-build:
	@if [ "$(QA_FRESH_DB)" = "1" ]; then \
		echo "[qa] QA_FRESH_DB=1: bajando stack y volúmenes..."; \
		docker compose down -v --remove-orphans; \
	fi
	docker compose up -d --build db backend frontend
	$(MAKE) qa-backend-wait

qa-backend-wait:
	docker compose exec -T backend bash -lc "python /app/qa/wait_backend_ready.py"

qa-ci-fresh:
	$(MAKE) QA_FRESH_DB=1 qa-ci

# Alias explícito para pipelines CI
qa-ci-ci: qa-ci-fresh

qa-static-scan:
	docker compose exec -T backend bash -lc "chmod +x /app/qa/static_scan_backend.sh && /app/qa/static_scan_backend.sh /app"

qa-backend-ruff:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && ruff check /app/backend/src | tee /app/$(QA_REPORTS_DIR)/ruff.txt"

qa-backend-mypy:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app && mypy --no-incremental --config-file mypy.ini backend/src | sed -E 's#^[^/]+/src#backend/src#' | tee /app/$(QA_REPORTS_DIR)/mypy.txt"

qa-backend-tests:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/backend && DJANGO_SETTINGS_MODULE=config.settings.test coverage run --rcfile /app/backend/.coveragerc -m pytest --junitxml=/app/$(QA_REPORTS_DIR)/pytest.xml && coverage xml --rcfile /app/backend/.coveragerc -o /app/$(QA_REPORTS_DIR)/coverage.xml && coverage report --rcfile /app/backend/.coveragerc | tee /app/$(QA_REPORTS_DIR)/coverage.txt"

qa-rbac-doctor:
	docker compose exec -T backend bash -lc "cd /app/backend && python manage.py seed_rbac_v01 && python manage.py rbac_doctor"

qa-audit-integrity:
	docker compose exec -T backend bash -lc "mkdir -p /app/$(QA_REPORTS_DIR) && cd /app/backend && python manage.py audit_verify_chain --seed-minimal --format json --output /app/$(QA_REPORTS_DIR)/audit_integrity.json"

qa-frontend-ci:
	docker compose --profile qa run --rm frontend_ci

# Gate 1: calidad estática + typecheck
qa-ci-gate1: qa-ci-up qa-static-scan qa-backend-ruff qa-backend-mypy qa-frontend-ci

# Gate 2: pruebas deterministas (pytest + cobertura)
qa-ci-gate2: qa-ci-up qa-backend-tests qa-rbac-doctor

# Gate 3: integridad de auditoría (reporte)
qa-ci-gate3: qa-ci-up qa-audit-integrity

# Runner completo Gates 1–3
qa-ci: qa-ci-gate1 qa-ci-gate2 qa-ci-gate3

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
	docker compose exec -T backend python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); u, _=User.objects.get_or_create(username='k6'); u.email='k6@test.com'; u.is_staff=True; u.set_password('Pass12345__Strong'); setattr(u, 'must_change_password', False); u.save(); print('K6_USER_READY')"

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

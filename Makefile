.PHONY: up down logs ps pipeline test build-frontend clean

# Démarre tous les services (MinIO, Kafka, Postgres, Airflow, API, frontend).
up:
	docker compose up -d --build

down:
	docker compose down

# Supprime aussi les volumes (réinitialisation complète des données).
down-clean:
	docker compose down -v

logs:
	docker compose logs -f

ps:
	docker compose ps

# Déclenche manuellement le pipeline complet bronze -> silver -> gold via la CLI Airflow.
pipeline:
	docker compose exec airflow-webserver airflow dags trigger ingestion_bronze

# Lance la suite de tests (pytest) en local, sans Docker.
test:
	pip install -r requirements-dev.txt -r api/requirements.txt --break-system-packages -q
	pytest tests/ -v

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete

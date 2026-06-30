"""
DAG : realtime_stream
----------------------
Système distribué temps-réel — remplace l'ancienne stack Kafka/Zookeeper.

Architecture : deux tâches Airflow indépendantes s'exécutent EN PARALLÈLE
toutes les 3 minutes via LocalExecutor (processus Python distincts) :

  ┌─────────────────────────┐   ┌─────────────────────────┐
  │  fetch_air_quality      │   │  fetch_velib             │
  │  WAQI → PostgreSQL      │   │  OpenData Paris → PG     │
  │  + pg_notify            │   │  + pg_notify             │
  └─────────────────────────┘   └─────────────────────────┘
             │                             │
             └──────────┬──────────────────┘
                        ▼
              WebSocket /ws/realtime  (LISTEN/NOTIFY)

Critère C2.2 : système distribué (tâches concurrentes sur processus séparés)
utilisant un mécanisme de streaming (pg_notify → push WebSocket temps-réel).
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "urban-data-explorer",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="realtime_stream",
    description="Collecte parallèle WAQI + Vélib → PostgreSQL + pg_notify (C2.2)",
    default_args=default_args,
    schedule="*/3 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["urban-data-explorer", "realtime", "streaming"],
) as dag:

    def _air_quality():
        from realtime_fetcher import fetch_and_store_air_quality
        return fetch_and_store_air_quality()

    def _velib():
        from realtime_fetcher import fetch_and_store_velib
        return fetch_and_store_velib()

    fetch_air_quality = PythonOperator(
        task_id="fetch_air_quality",
        python_callable=_air_quality,
    )

    fetch_velib = PythonOperator(
        task_id="fetch_velib",
        python_callable=_velib,
    )

    # Pas de dépendance entre les deux tâches → exécution parallèle
    [fetch_air_quality, fetch_velib]

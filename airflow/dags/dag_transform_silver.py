"""
DAG : transform_silver
------------------------
Nettoie, valide et géocode les données brutes (zone BRONZE) puis écrit des
fichiers Parquet propres en zone SILVER. Déclenché par `ingestion_bronze`,
déclenche ensuite `aggregate_gold`.

Compétence visée : C3.1 (préparation/nettoyage des données, qualité documentée),
C2.3 (transformation et intégration multi-sources).
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "urban-data-explorer",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="transform_silver",
    description="Nettoyage, validation qualité et géocodage -> zone Silver",
    default_args=default_args,
    schedule=None,  # déclenché uniquement par ingestion_bronze
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["urban-data-explorer", "silver"],
) as dag:

    clean_data = BashOperator(
        task_id="clean_and_validate",
        bash_command="cd /opt/airflow/pipeline/silver && python clean_silver.py",
    )

    trigger_gold = TriggerDagRunOperator(
        task_id="trigger_aggregate_gold",
        trigger_dag_id="aggregate_gold",
        wait_for_completion=False,
    )

    clean_data >> trigger_gold

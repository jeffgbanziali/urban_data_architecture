"""
DAG : ingestion_bronze
-----------------------
Récupère les sources ouvertes (DVF, INSEE, OpenData Paris, Airparif...) et les
dépose en zone BRONZE du data lake MinIO. Déclenche ensuite le DAG
`transform_silver`, conformément au schéma d'architecture du projet.

Compétences visées : C1.3 (Data Lake sécurisé, sources variées), C1.4 (résilience :
chaque source est gérée indépendamment, voir ingestion/download_sources.py),
C2.4 (mesure de performance : durée par source loggée + rapport JSON en bronze).
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
    dag_id="ingestion_bronze",
    description="Téléchargement des sources ouvertes vers la zone Bronze (MinIO)",
    default_args=default_args,
    schedule="0 2 * * *",  # tous les jours à 2h du matin
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["urban-data-explorer", "bronze"],
) as dag:

    ingest_sources = BashOperator(
        task_id="ingest_sources",
        bash_command=(
            "cd /opt/airflow/pipeline/bronze && "
            "python download_sources.py"
        ),
    )

    trigger_silver = TriggerDagRunOperator(
        task_id="trigger_transform_silver",
        trigger_dag_id="transform_silver",
        wait_for_completion=False,
    )

    ingest_sources >> trigger_silver

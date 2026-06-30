from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "urban-data-explorer",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="aggregate_gold",
    description="Agrégations métier -> PostgreSQL Gold + exports MinIO",
    default_args=default_args,
    schedule=None,  # déclenché uniquement par transform_silver
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["urban-data-explorer", "gold"],
) as dag:

    aggregate = BashOperator(
        task_id="aggregate_and_load_postgres",
        bash_command="cd /opt/airflow/pipeline/gold && python aggregate_gold.py",
    )

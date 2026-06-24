"""
common/minio_client.py
----------------------
Wrapper boto3 pour MinIO. Centralise la connexion, le versioning horodaté
et la gestion d'erreurs pour les trois couches bronze/silver/gold.
"""
import io
import os
import json
import logging
from datetime import datetime, timezone

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("minio_client")


def get_s3_client():
    """Crée un client S3 pointant vers MinIO, à partir des variables d'environnement."""
    endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
    return boto3.client(
        "s3",
        endpoint_url=f"http://{endpoint}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket(client, bucket: str):
    """Crée le bucket s'il n'existe pas encore (idempotent)."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
        logger.info("Bucket créé : %s", bucket)


def put_bytes(client, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"):
    """Écrit un objet binaire dans un bucket, avec gestion d'erreur explicite."""
    ensure_bucket(client, bucket)
    try:
        client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        logger.info("Écrit s3://%s/%s (%d octets)", bucket, key, len(data))
        return True
    except ClientError as e:
        logger.error("Échec écriture s3://%s/%s : %s", bucket, key, e)
        return False


def put_dataframe_as_parquet(client, bucket: str, key: str, df):
    """Sérialise un DataFrame pandas en Parquet et l'envoie sur MinIO."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    return put_bytes(client, bucket, key, buffer.getvalue(), content_type="application/octet-stream")


def put_dataframe_as_csv(client, bucket: str, key: str, df):
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return put_bytes(client, bucket, key, buffer.getvalue().encode("utf-8"), content_type="text/csv")


def put_json(client, bucket: str, key: str, obj):
    payload = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    return put_bytes(client, bucket, key, payload, content_type="application/json")


def get_bytes(client, bucket: str, key: str) -> bytes:
    resp = client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def list_keys(client, bucket: str, prefix: str = ""):
    """Liste les clés d'un bucket pour un préfixe donné (pagination gérée)."""
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def versioned_prefix(source_name: str) -> str:
    """Construit un préfixe horodaté YYYY/MM/DD/HHMMSS pour le versioning par exécution."""
    now = datetime.now(timezone.utc)
    return f"{source_name}/{now:%Y/%m/%d}/{now:%H%M%S}"

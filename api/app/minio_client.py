import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


def get_s3_client():
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


def try_get_bytes(bucket: str, key: str) -> bytes | None:
    """Retourne le contenu de l'objet, ou None si MinIO est indisponible ou
    si l'objet n'existe pas encore (ex. le pipeline n'a pas encore tourné)."""
    try:
        client = get_s3_client()
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    except ClientError:
        return None
    except Exception:
        return None

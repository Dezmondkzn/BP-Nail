from pathlib import Path
import re
import boto3
from botocore.config import Config


def valid_key(key):
    if not re.fullmatch(r"[a-zA-Z0-9_./-]+", key) or ".." in key or key.startswith("/"):
        raise ValueError("Invalid storage key")
    return key


class LocalStorage:
    """Development only. Never expose this directory via HTTP."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def put(self, key, data, content_type):
        path = self.root / valid_key(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(data)
        path.chmod(0o600)

    def get(self, key):
        return (self.root / valid_key(key)).read_bytes()


class S3Storage:
    def __init__(self, settings):
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.aws_default_region,
            config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}),
        )

    def put(self, key, data, content_type):
        # No public ACL and no public/signed URLs are returned to clients.
        self.client.put_object(Bucket=self.bucket, Key=valid_key(key), Body=data, ContentType=content_type)

    def get(self, key):
        response = self.client.get_object(Bucket=self.bucket, Key=valid_key(key))
        with response["Body"] as stream:
            return stream.read()


def storage(settings):
    return (
        S3Storage(settings) if settings.storage_backend == "s3" else LocalStorage(settings.local_storage_path)
    )

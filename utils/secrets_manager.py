"""
Helpers to hydrate environment variables from AWS Secrets Manager.
"""
from __future__ import annotations

import json
import os
from typing import Any

import boto3


DEFAULT_SECRET_ID = "BradBot/creds"


def load_secret_env(secret_id: str | None = None, *, region_name: str | None = None) -> bool:
    """
    Fetch a JSON-formatted secret from AWS Secrets Manager and merge it into os.environ.

    The secret ID defaults to the SECRETS_MANAGER_ID (or AWS_SECRET_ID) environment variable
    so deployments can configure it without code changes.

    Returns True if a secret was loaded successfully, otherwise False (with a console message).
    """
    secret_id = secret_id or os.getenv("SECRETS_MANAGER_ID") or os.getenv("AWS_SECRET_ID") or DEFAULT_SECRET_ID
    if not secret_id:
        return False

    region_name = region_name or os.getenv("AWS_REGION", "us-east-1")

    try:
        client = boto3.client("secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_id)
        secret_string = response.get("SecretString")
        if not secret_string:
            print(f"[Secrets] Secret {secret_id} did not contain SecretString data.")
            return False

        payload: dict[str, Any] = json.loads(secret_string)
        for key, value in payload.items():
            if value is not None:
                os.environ[key] = str(value)
        print(f"[Secrets] Loaded environment values from {secret_id}.")
        return True
    except Exception as exc:
        print(f"[Secrets] Failed to load {secret_id}: {exc}")
        return False

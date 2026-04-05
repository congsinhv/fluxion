import os

from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")
APPSYNC_ENDPOINT = os.environ.get("APPSYNC_ENDPOINT", "")
IDEMPOTENCY_TABLE_NAME = os.environ.get("IDEMPOTENCY_TABLE_NAME", "")

logger = Logger()
tracer = Tracer()

import os

import boto3
from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
IDEMPOTENCY_TABLE_NAME = os.environ.get("IDEMPOTENCY_TABLE_NAME", "")

logger = Logger()
tracer = Tracer()
sns_client = boto3.client("sns")

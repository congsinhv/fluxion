import os

import boto3
from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")

logger = Logger()
tracer = Tracer()
sqs_client = boto3.client("sqs")

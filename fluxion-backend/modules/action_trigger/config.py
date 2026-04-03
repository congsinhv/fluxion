import os

from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

logger = Logger()
tracer = Tracer()

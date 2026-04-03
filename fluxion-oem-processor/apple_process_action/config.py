import os

from aws_lambda_powertools import Logger, Tracer

CACHE_ENDPOINT = os.environ.get("CACHE_ENDPOINT", "")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
API_GATEWAY_URL = os.environ.get("API_GATEWAY_URL", "")

logger = Logger()
tracer = Tracer()

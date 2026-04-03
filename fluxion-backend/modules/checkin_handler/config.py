import os

from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")
APPSYNC_ENDPOINT = os.environ.get("APPSYNC_ENDPOINT", "")
APPSYNC_API_KEY = os.environ.get("APPSYNC_API_KEY", "")

logger = Logger()
tracer = Tracer()

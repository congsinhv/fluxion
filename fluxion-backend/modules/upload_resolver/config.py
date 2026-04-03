import os

from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")

logger = Logger()
tracer = Tracer()

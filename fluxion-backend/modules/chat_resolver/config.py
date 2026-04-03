import os

from aws_lambda_powertools import Logger, Tracer

DATABASE_URL = os.environ.get("DATABASE_URL", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

logger = Logger()
tracer = Tracer()

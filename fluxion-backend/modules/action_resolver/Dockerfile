# action_resolver Lambda container image.
# Self-contained: no dependency on a workspace-built base image.
# Build context (from CI/.github/workflows/deploy.yml): fluxion-backend/

FROM public.ecr.aws/lambda/python:3.12

# Runtime deps mirror modules/action_resolver/pyproject.toml.
# boto3 is required for SQS SendMessage (action_trigger queue).
RUN pip install --no-cache-dir \
    "psycopg[binary]>=3.1,<4" \
    "pydantic>=2.6" \
    "aws-lambda-powertools>=2.30" \
    "boto3>=1.34"

# Source — flat-COPY into LAMBDA_TASK_ROOT so imports resolve as
# `from config import X` (mirrors pytest pythonpath = ["src"]).
COPY modules/action_resolver/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

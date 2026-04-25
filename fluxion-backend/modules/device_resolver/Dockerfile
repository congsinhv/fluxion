# device_resolver Lambda container image.
# Self-contained: no dependency on a workspace-built base image.
# Build context (from CI/.github/workflows/deploy.yml): fluxion-backend/

FROM public.ecr.aws/lambda/python:3.12

# Runtime deps mirror modules/device_resolver/pyproject.toml.
RUN pip install --no-cache-dir \
    "psycopg[binary]>=3.1,<4" \
    "pydantic>=2.6" \
    "aws-lambda-powertools>=2.30"

COPY modules/device_resolver/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

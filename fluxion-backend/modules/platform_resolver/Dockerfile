# platform_resolver Lambda container image.
# Self-contained: no dependency on a workspace-built base image.
# Build context (from CI/.github/workflows/deploy.yml): fluxion-backend/

FROM public.ecr.aws/lambda/python:3.12

# Runtime deps mirror modules/platform_resolver/pyproject.toml.
# Cached layer — only invalidated when this list changes.
RUN pip install --no-cache-dir \
    "psycopg[binary]>=3.1,<4" \
    "pydantic>=2.6" \
    "aws-lambda-powertools>=2.30"

# Source — invalidates on any code change but deps stay cached above.
COPY modules/platform_resolver/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

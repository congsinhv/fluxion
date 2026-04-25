# Template Lambda container image — copy this when scaffolding a new resolver.
# Self-contained: no dependency on a workspace-built base image.
# Build context (from CI/.github/workflows/deploy.yml): fluxion-backend/

FROM public.ecr.aws/lambda/python:3.12

# Runtime deps mirror modules/_template/pyproject.toml.
# When scaffolding a real Lambda, update this list to match the new module's deps.
RUN pip install --no-cache-dir \
    "psycopg[binary]>=3.1,<4" \
    "pydantic>=2.6" \
    "aws-lambda-powertools>=2.30"

# Source — flat-COPY into LAMBDA_TASK_ROOT so imports resolve as
# `from config import X` (mirrors pytest pythonpath = ["src"]).
COPY modules/_template/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

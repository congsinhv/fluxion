# user_resolver Lambda container image.
# Self-contained: no dependency on a workspace-built base image.
# Build context (from CI/.github/workflows/deploy.yml): fluxion-backend/

FROM public.ecr.aws/lambda/python:3.12

# Runtime deps mirror modules/user_resolver/pyproject.toml.
# boto3 is required for Cognito admin operations (admin_create_user, etc.).
RUN pip install --no-cache-dir \
    "psycopg[binary]>=3.1,<4" \
    "pydantic>=2.6" \
    "aws-lambda-powertools>=2.30" \
    "boto3>=1.34"

COPY modules/user_resolver/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

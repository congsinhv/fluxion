FROM fluxion-backend/resolver-base:latest

# user_resolver requires boto3 for Cognito admin operations.
# The resolver-base image only installs psycopg/pydantic/powertools;
# boto3 is available in the AWS Lambda runtime but must be added here
# so that the container image works correctly in integration tests.
RUN uv pip install --system --no-cache "boto3>=1.34"

COPY src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

# Inherits from the workspace-level base image built from Dockerfile.resolver.
# Build the base first: docker build -f Dockerfile.resolver -t fluxion-backend/resolver-base:latest .
FROM fluxion-backend/resolver-base:latest

# Copy src/ contents flat into LAMBDA_TASK_ROOT so imports resolve as
# `from config import X` rather than `from src.config import X`.
# This mirrors pytest pythonpath = ["src"] at test time.
COPY src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

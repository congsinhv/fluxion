# Per-module image. Inherits tooling from the repo-root base image.
# Build the base first:
#   docker build -f ../../Dockerfile.worker -t fluxion-oem-processor/worker-base:latest ../..
# Then build this module:
#   docker build -t _template:latest .
FROM fluxion-oem-processor/worker-base:latest

# Install runtime dependencies declared in this module's pyproject.toml.
COPY pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Copy src/ contents flat into LAMBDA_TASK_ROOT so Lambda resolves imports as
# `from config import X` rather than `from src.config import X`.
COPY src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

# Self-contained smoketest Lambda image — no reliance on resolver-base.
# Used by TC-03 to verify ECR-push matrix works end-to-end in CI.
FROM public.ecr.aws/lambda/python:3.12

COPY modules/smoketest/src/ ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]

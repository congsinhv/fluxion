from aws_lambda_powertools.utilities.typing import LambdaContext
from config import logger, tracer


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda handler for platform_resolver."""
    raise NotImplementedError

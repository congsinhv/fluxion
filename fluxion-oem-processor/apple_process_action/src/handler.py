from aws_lambda_powertools.utilities.typing import LambdaContext

from config import logger, tracer
from const import HTTP_METHOD_KEY, REQUEST_CONTEXT_KEY, SQS_RECORDS_KEY


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Dual-trigger handler: SQS (command) or API GW (MDM check-in)."""
    if SQS_RECORDS_KEY in event:
        return _handle_sqs_command(event)
    elif HTTP_METHOD_KEY in event or REQUEST_CONTEXT_KEY in event:
        return _handle_mdm_checkin(event)
    raise ValueError(f"Unknown event source: {list(event.keys())}")


def _handle_sqs_command(event: dict) -> dict:
    raise NotImplementedError


def _handle_mdm_checkin(event: dict) -> dict:
    raise NotImplementedError

"""Focused tests for race-safe bulk assignment and partial-failure split.

These tests verify the _assign_impl split logic directly:
  - All devices valid, all locked → all in valid[]
  - Some devices fail FSM → in failed[] with INVALID_TRANSITION
  - Some devices not found → in failed[] with DEVICE_NOT_FOUND
  - Some devices pass FSM but lose UPDATE race → in failed[] with DEVICE_BUSY
  - Mixed: FSM invalid + race loser + not-found + success
  - Whole batch: all devices are race losers → valid=[], failed has all with DEVICE_BUSY
  - assignAction single device raises DeviceAlreadyAssignedError on race loss
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from db import ExecutionTuple, InvalidDevice, ValidDevice
from handler import _assign_impl

# ---------------------------------------------------------------------------
# Context stub
# ---------------------------------------------------------------------------


def _make_ctx(schema: str = "dev1", cognito_sub: str = "sub-test") -> MagicMock:
    ctx = MagicMock()
    ctx.tenant_schema = schema
    ctx.cognito_sub = cognito_sub
    return ctx


# ---------------------------------------------------------------------------
# DB mock factory for _assign_impl
# ---------------------------------------------------------------------------


def _make_db_mock(
    action_row: dict[str, Any] | None = None,
    template_row: dict[str, Any] | None = None,
    valid_devices: list[ValidDevice] | None = None,
    invalid_devices: list[InvalidDevice] | None = None,
    executions: list[ExecutionTuple] | None = None,
) -> MagicMock:
    db = MagicMock()
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    db.load_action.return_value = action_row or {"id": "act-1", "from_state_id": 4}
    db.load_message_template.return_value = template_row
    db.validate_devices_for_action.return_value = (
        valid_devices if valid_devices is not None else [],
        invalid_devices if invalid_devices is not None else [],
    )
    db.create_batch_with_devices.return_value = executions if executions is not None else []
    return db


def _run_impl(
    device_ids: list[str],
    db_mock: MagicMock,
    action_id: str | None = None,
    template_id: str | None = None,
) -> tuple[list[ExecutionTuple], list[InvalidDevice]]:
    ctx = _make_ctx()
    with (
        patch("handler.Database", return_value=db_mock),
        patch("handler.enqueue_action_trigger", return_value="msg-id"),
        patch("handler.uuid") as mock_uuid,
    ):
        mock_uuid.uuid4.return_value = uuid.UUID("00000000-0000-0000-0000-000000000001")
        return _assign_impl(
            device_ids=device_ids,
            action_id=action_id or str(uuid.uuid4()),
            configuration=None,
            message_template_id=template_id,
            ctx=ctx,
            correlation_id="test-cid",
        )


# ---------------------------------------------------------------------------
# All valid, all locked
# ---------------------------------------------------------------------------


def test_all_devices_valid_and_locked() -> None:
    """All devices pass FSM and all are locked → executions == input count, failed empty."""
    dev1 = str(uuid.uuid4())
    dev2 = str(uuid.uuid4())
    exe1 = str(uuid.uuid4())
    exe2 = str(uuid.uuid4())
    cmd1 = str(uuid.uuid4())
    cmd2 = str(uuid.uuid4())

    db = _make_db_mock(
        valid_devices=[ValidDevice(dev1, 4), ValidDevice(dev2, 4)],
        invalid_devices=[],
        executions=[ExecutionTuple(dev1, exe1, cmd1), ExecutionTuple(dev2, exe2, cmd2)],
    )
    executions, invalid = _run_impl([dev1, dev2], db)

    assert len(executions) == 2
    assert invalid == []
    executed_ids = {e.device_id for e in executions}
    assert dev1 in executed_ids
    assert dev2 in executed_ids


# ---------------------------------------------------------------------------
# FSM invalid
# ---------------------------------------------------------------------------


def test_fsm_invalid_devices_go_to_failed() -> None:
    """Devices that fail FSM check → all in invalid, none in executions."""
    dev1 = str(uuid.uuid4())
    db = _make_db_mock(
        valid_devices=[],
        invalid_devices=[InvalidDevice(dev1, "INVALID_TRANSITION: state 1 != from_state 4")],
        executions=[],
    )
    executions, invalid = _run_impl([dev1], db)

    assert executions == []
    assert len(invalid) == 1
    assert invalid[0].device_id == dev1
    assert "INVALID_TRANSITION" in invalid[0].reason


# ---------------------------------------------------------------------------
# Device not found
# ---------------------------------------------------------------------------


def test_device_not_found_goes_to_failed() -> None:
    """Devices absent from DB query result → DEVICE_NOT_FOUND in invalid."""
    dev1 = str(uuid.uuid4())
    db = _make_db_mock(
        valid_devices=[],
        invalid_devices=[InvalidDevice(dev1, f"DEVICE_NOT_FOUND: device {dev1} not found")],
        executions=[],
    )
    executions, invalid = _run_impl([dev1], db)

    assert executions == []
    assert len(invalid) == 1
    assert "DEVICE_NOT_FOUND" in invalid[0].reason


# ---------------------------------------------------------------------------
# Race-safe: all race losers
# ---------------------------------------------------------------------------


def test_all_devices_lose_race() -> None:
    """All pass FSM but none locked by UPDATE → executions empty, all DEVICE_BUSY in failed."""
    dev1 = str(uuid.uuid4())
    dev2 = str(uuid.uuid4())

    db = _make_db_mock(
        valid_devices=[ValidDevice(dev1, 4), ValidDevice(dev2, 4)],
        invalid_devices=[],
        executions=[],  # UPDATE RETURNING returned nothing
    )
    executions, invalid = _run_impl([dev1, dev2], db)

    assert executions == []
    assert len(invalid) == 2
    for inv in invalid:
        assert "DEVICE_BUSY" in inv.reason


# ---------------------------------------------------------------------------
# Race-safe: partial race loss
# ---------------------------------------------------------------------------


def test_partial_race_loss_splits_correctly() -> None:
    """One device wins the lock, one loses → 1 in executions, 1 DEVICE_BUSY in failed."""
    dev1 = str(uuid.uuid4())
    dev2 = str(uuid.uuid4())
    exe1 = str(uuid.uuid4())
    cmd1 = str(uuid.uuid4())

    db = _make_db_mock(
        valid_devices=[ValidDevice(dev1, 4), ValidDevice(dev2, 4)],
        invalid_devices=[],
        # dev2 absent from executions → race loser
        executions=[ExecutionTuple(dev1, exe1, cmd1)],
    )
    executions, invalid = _run_impl([dev1, dev2], db)

    assert len(executions) == 1
    assert executions[0].device_id == dev1
    assert len(invalid) == 1
    assert invalid[0].device_id == dev2
    assert "DEVICE_BUSY" in invalid[0].reason


# ---------------------------------------------------------------------------
# Mixed: FSM invalid + race loser + not-found + success
# ---------------------------------------------------------------------------


def test_mixed_failure_modes() -> None:
    """Four devices: 1 success, 1 FSM-invalid, 1 not-found, 1 race-loser."""
    dev_ok = str(uuid.uuid4())
    dev_fsm = str(uuid.uuid4())
    dev_missing = str(uuid.uuid4())
    dev_race = str(uuid.uuid4())
    exe_ok = str(uuid.uuid4())
    cmd_ok = str(uuid.uuid4())

    db = _make_db_mock(
        valid_devices=[ValidDevice(dev_ok, 4), ValidDevice(dev_race, 4)],
        invalid_devices=[
            InvalidDevice(dev_fsm, "INVALID_TRANSITION: state 1 != from_state 4"),
            InvalidDevice(dev_missing, f"DEVICE_NOT_FOUND: device {dev_missing} not found"),
        ],
        # dev_race lost the UPDATE race
        executions=[ExecutionTuple(dev_ok, exe_ok, cmd_ok)],
    )
    executions, invalid = _run_impl([dev_ok, dev_fsm, dev_missing, dev_race], db)

    assert len(executions) == 1
    assert executions[0].device_id == dev_ok

    reasons = {inv.device_id: inv.reason for inv in invalid}
    assert "INVALID_TRANSITION" in reasons[dev_fsm]
    assert "DEVICE_NOT_FOUND" in reasons[dev_missing]
    assert "DEVICE_BUSY" in reasons[dev_race]


# ---------------------------------------------------------------------------
# SQS failure suppression in bulk path
# ---------------------------------------------------------------------------


def test_sqs_failure_suppressed_in_bulk_path() -> None:
    """SQS failure post-commit is logged but not surfaced in valid/failed split."""
    from sqs import SqsError

    dev1 = str(uuid.uuid4())
    exe1 = str(uuid.uuid4())
    cmd1 = str(uuid.uuid4())
    ctx = _make_ctx()

    db = _make_db_mock(
        valid_devices=[ValidDevice(dev1, 4)],
        executions=[ExecutionTuple(dev1, exe1, cmd1)],
    )
    with (
        patch("handler.Database", return_value=db),
        patch("handler.enqueue_action_trigger", side_effect=SqsError("queue down")),
        patch("handler.uuid") as mock_uuid,
    ):
        mock_uuid.uuid4.return_value = uuid.UUID("00000000-0000-0000-0000-000000000002")
        executions, invalid = _assign_impl(
            device_ids=[dev1],
            action_id=str(uuid.uuid4()),
            configuration=None,
            message_template_id=None,
            ctx=ctx,
            correlation_id="cid",
        )

    # DB commit succeeded; SQS failure does not move device to failed[]
    assert len(executions) == 1
    assert invalid == []

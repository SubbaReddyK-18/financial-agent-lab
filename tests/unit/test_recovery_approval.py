"""Focused tests for the Block 9 human approval boundary."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.api.security.auth import require_configured_admin_auth
from apps.api.settings import Settings
from domain.recovery.approval_service import approve_recovery_action, reject_recovery_action
from domain.recovery.control_plane import RecoveryActionControlPlane
from domain.shared.enums import RecoveryActionStatus, RecoveryActionType
from domain.shared.errors import InvalidActionError


def _pending_action() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), recovery_case_id=uuid.uuid4(),
        idempotency_key="approval-test-key", status="PENDING_APPROVAL",
        action_type="NOTIFY", failure_reason=None,
    )


@pytest.mark.asyncio
async def test_approval_transitions_and_queues_exactly_one_dispatch_with_audit_fields():
    action = _pending_action()
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[action, None])
    session.flush = AsyncMock()

    result = await approve_recovery_action(
        action.id, "admin_api_key:abcd", session, "cid-approval", "reviewed"
    )

    assert result.status == RecoveryActionStatus.APPROVED.value
    added = [call.args[0] for call in session.add.call_args_list]
    approval = next(x for x in added if x.__tablename__ == "recovery_action_approvals")
    outbox = next(x for x in added if x.__tablename__ == "recovery_outbox_events")
    assert approval.actor_id == "admin_api_key:abcd"
    assert approval.correlation_id == "cid-approval"
    assert approval.reason == "reviewed"
    assert approval.decision == "APPROVED"
    assert outbox.recovery_action_id == action.id
    assert outbox.status == "PENDING"
    assert outbox.idempotency_key == "outbox_approval-test-key"
    assert session.flush.await_count == 1


@pytest.mark.asyncio
async def test_duplicate_or_concurrent_replay_is_suppressed_by_locked_action_and_existing_record():
    action = _pending_action()
    existing = SimpleNamespace(decision="APPROVED")
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[action, existing])
    session.flush = AsyncMock()

    result = await approve_recovery_action(action.id, "actor", session)

    assert result is action
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "CANCELLED", "EXPIRED", "SUPERSEDED"])
async def test_terminal_actions_cannot_be_approved(status):
    action = _pending_action()
    action.status = status
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[action, None])
    with pytest.raises(InvalidActionError):
        await approve_recovery_action(action.id, "actor", session)
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_rejection_cancels_pending_action_without_dispatch():
    action = _pending_action()
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[action, None])
    session.flush = AsyncMock()

    result = await reject_recovery_action(action.id, "actor", session, reason="merchant declined")

    assert result.status == "CANCELLED"
    added = [call.args[0] for call in session.add.call_args_list]
    assert len(added) == 1
    assert added[0].decision == "REJECTED"
    assert action.failure_reason == "merchant declined"


@pytest.mark.asyncio
async def test_control_plane_refuses_pending_approval_dispatch_without_execution():
    action = _pending_action()
    session = MagicMock()
    # The approval lifecycle intentionally creates no outbox until approval.
    session.scalar = AsyncMock(side_effect=[action, None])

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session)

    assert result.status == "PENDING_APPROVAL"
    assert result.execution_reference.startswith("IDEMPOTENT_SKIPPED_")
    assert action.status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_approval_gated_action_has_no_outbox_until_human_approval():
    session = MagicMock()
    session.flush = AsyncMock()
    case = SimpleNamespace(id=uuid.uuid4(), payment_id=uuid.uuid4(), actions=[])

    action, outbox = await RecoveryActionControlPlane().create_approved_action_with_outbox(
        case=case, action_type=RecoveryActionType.NOTIFY, discount_percent=0,
        session=session, requires_approval=True,
    )

    assert action.status == "PENDING_APPROVAL"
    assert outbox is None
    assert session.add.call_count == 1


@pytest.mark.asyncio
async def test_approval_requires_a_configured_authenticated_admin_key():
    with pytest.raises(HTTPException) as exc:
        await require_configured_admin_auth(api_key=None, settings=Settings(admin_api_key=None))
    assert exc.value.status_code == 503

    with pytest.raises(HTTPException) as exc:
        await require_configured_admin_auth(api_key=None, settings=Settings(admin_api_key="key"))
    assert exc.value.status_code == 401

    actor = await require_configured_admin_auth(api_key="key", settings=Settings(admin_api_key="key"))
    assert actor.startswith("admin_api_key:")
    assert actor != "admin_api_key:key"
    assert actor == "admin_api_key:2c70e12b7a0646f9"

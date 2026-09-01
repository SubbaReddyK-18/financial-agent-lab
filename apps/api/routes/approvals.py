import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from apps.api.middleware.correlation import get_correlation_id
from apps.api.security.auth import require_configured_admin_auth
from domain.recovery.approval_service import approve_recovery_action, reject_recovery_action
from infrastructure.database.connection import get_db_session
router = APIRouter(prefix="/recovery-actions", tags=["Recovery approvals"])
class ApprovalRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


@router.post("/{action_id}/approve")
async def approve(action_id: uuid.UUID, body: ApprovalRequest, session: AsyncSession = Depends(get_db_session), actor_id: str = Depends(require_configured_admin_auth)):
    action = await approve_recovery_action(action_id, actor_id, session, get_correlation_id(), body.reason)
    return {"action_id": str(action.id), "status": action.status, "execution": "queued"}


@router.post("/{action_id}/reject")
async def reject(action_id: uuid.UUID, body: ApprovalRequest, session: AsyncSession = Depends(get_db_session), actor_id: str = Depends(require_configured_admin_auth)):
    action = await reject_recovery_action(action_id, actor_id, session, get_correlation_id(), body.reason)
    return {"action_id": str(action.id), "status": action.status, "execution": "not_queued"}

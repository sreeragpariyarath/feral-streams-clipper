"""Team helper routes (invitation emails, team AI edit/billing usage lookup)."""

from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth_headers import get_authenticated_user_id, resolve_auth_context
from ...config import get_config
from ...database import get_db
from ...repositories.team_repository import TEAM_MANAGER_ROLES, TeamRepository
from ...services.ai_edit_allowance_service import AIEditAllowanceService
from ...services.billing_service import BillingService

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/{team_id}/usage")
async def get_team_usage(
    team_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return pooled video-minute and AI-edit usage for a team the caller belongs to."""
    config = get_config()
    auth_ctx = await resolve_auth_context(request, db, config)
    role = await TeamRepository.get_member_role(db, team_id, auth_ctx.user_id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this team")
    if auth_ctx.via_api_key and auth_ctx.team_id != team_id:
        raise HTTPException(status_code=403, detail="API key is not scoped to this team")

    billing_service = BillingService(db, config)
    billing = await billing_service.get_usage_summary(
        auth_ctx.user_id, team_id=team_id
    )
    ai_edits = await AIEditAllowanceService(db, config).summary(
        auth_ctx.user_id, team_id=team_id
    )
    member_usage = await billing_service.get_team_member_usage_map(
        team_id,
        only_user_id=None if role in TEAM_MANAGER_ROLES else auth_ctx.user_id,
    )
    return {"billing": billing, "ai_edits": ai_edits, "member_usage": member_usage}

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Optional
from pydantic import BaseModel, field_validator
import uuid

from app.core.ai_agent import (
    generate_insight_for_link,
    generate_comparison_insight,
    generate_campaign_proposal,
    CampaignProposalResponse,
    CampaignPromptRequest
)
from app.core.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.crud.link import short_code_exists


class InsightRequest(BaseModel):
    user_prompt: str | None = None





class CompareRequest(BaseModel):
    link_ids: list[uuid.UUID]

    @field_validator("link_ids")
    @classmethod
    def validate_count(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not (2 <= len(v) <= 4):
            raise ValueError("Select between 2 and 4 links to compare.")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate link IDs are not allowed.")
        return v


router = APIRouter(prefix="/ai", tags=["AI Analyst"])


@router.get("/check-short-code")
async def check_custom_code(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    exists = await short_code_exists(db, code)
    return {"exists": exists}


@router.post("/insights/link/{link_id}")
async def get_link_insight(
    link_id: uuid.UUID,
    request: InsightRequest,
    current_user: User = Depends(get_current_user),
):
    """Generates a natural language insight report for a specific link."""
    insight_text = await generate_insight_for_link(
        str(link_id), str(current_user.id), request.user_prompt
    )
    if "Unauthorized" in insight_text:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this link.")
    if "Link not found" in insight_text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found.")
    return {"insight": insight_text}


@router.post("/propose-campaign", response_model=CampaignProposalResponse)
async def propose_campaign(
    request: CampaignPromptRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Parses a natural language prompt and returns a structured campaign proposal.
    """
    try:
        proposal = await generate_campaign_proposal(request.prompt)
        return proposal
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate campaign proposal: {str(e)}")


@router.post("/compare")
async def compare_links(
    request: CompareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generates an AI comparative analysis report for 2–4 links.
    Verifies ownership of every link before generating the report.
    """
    insight_text = await generate_comparison_insight(
        link_ids=[str(lid) for lid in request.link_ids],
        user_id=str(current_user.id),
        db=db,
    )

    if insight_text.startswith("Unauthorized"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=insight_text)
    if insight_text.startswith("Link not found"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=insight_text)

    return {"insight": insight_text}


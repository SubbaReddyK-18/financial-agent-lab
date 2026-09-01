"""
apps/api/routes/webhooks.py

Razorpay Test Mode webhook ingestion route.

SECURITY & ARCHITECTURAL RULES (Block 2, Steps 2, 3, 4):
1. Raw request body is read and signature verified BEFORE any JSON parsing.
2. Signatures are verified using constant-time HMAC-SHA256 comparison.
3. If signature verification fails, reject immediately with 401.
4. Idempotency: duplicate X-Razorpay-Event-Id values are caught and acknowledged
   cleanly with 200 OK (duplicate_ignored) without creating duplicate side effects.
5. Ingestion only persists to durable inbox (razorpay_webhook_events) with status RECEIVED;
   heavy reconciliation is performed asynchronously by workers.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.settings import Settings, get_settings
from infrastructure.database.connection import get_db_session
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.gateways.razorpay.parser import (
    RazorpayPayloadError,
    parse_razorpay_webhook_payload,
)
from infrastructure.security.webhook_verifier import verify_razorpay_signature

logger = logging.getLogger("apps.api.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
    summary="Ingest Razorpay Test Mode webhook events",
)
async def ingest_razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
) -> dict:
    """
    Ingest, authenticate, deduplicate, and persist incoming Razorpay webhook events.
    """
    # 1. Validate required security headers
    if not x_razorpay_signature or not x_razorpay_event_id:
        logger.warning("Rejected webhook: missing required Razorpay headers")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required headers: X-Razorpay-Signature and X-Razorpay-Event-Id.",
        )

    # 2. Extract raw request body bytes
    raw_body = await request.body()
    if not raw_body:
        logger.warning("Rejected webhook: empty request body")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body cannot be empty.",
        )

    # 3. Authenticate signature against raw body bytes BEFORE parsing JSON
    is_valid = verify_razorpay_signature(
        raw_body=raw_body,
        signature=x_razorpay_signature,
        secret=settings.razorpay_webhook_secret,
    )
    if not is_valid:
        logger.warning("Rejected webhook: invalid HMAC signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    # 4. Parse JSON payload
    try:
        payload_dict = json.loads(raw_body.decode("utf-8"))
    except Exception:
        logger.warning("Rejected webhook: payload is not valid JSON")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body.",
        )

    # 5. Validate event envelope
    try:
        parsed_event = parse_razorpay_webhook_payload(
            payload_dict=payload_dict,
            event_id_header=x_razorpay_event_id.strip(),
        )
    except RazorpayPayloadError as e:
        logger.warning("Rejected webhook: invalid envelope structure: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event structure: {e}",
        )

    # 6. Deduplicate & persist into durable inbox
    existing_event = await db.scalar(
        select(RazorpayWebhookEventORM).where(
            RazorpayWebhookEventORM.razorpay_event_id == parsed_event.event_id
        )
    )
    if existing_event is not None:
        logger.info(
            "Duplicate webhook event %r received (status: %s); acknowledging duplicate.",
            parsed_event.event_id,
            existing_event.processing_status,
        )
        return {
            "status": "duplicate_ignored",
            "event_id": parsed_event.event_id,
        }

    correlation_id = str(uuid.uuid4())
    webhook_orm = RazorpayWebhookEventORM(
        id=uuid.uuid4(),
        razorpay_event_id=parsed_event.event_id,
        event_type=parsed_event.event_type,
        account_id=parsed_event.account_id,
        payload=parsed_event.raw_dict,
        raw_payload=raw_body.decode("utf-8", errors="replace"),
        signature=x_razorpay_signature,
        event_created_at=parsed_event.event_created_at,
        processing_status="RECEIVED",
        correlation_id=correlation_id,
    )

    try:
        db.add(webhook_orm)
        await db.flush()
    except IntegrityError:
        # Concurrent duplicate delivery race condition caught by PostgreSQL unique constraint
        await db.rollback()
        logger.info("Concurrent duplicate delivery caught for event %r", parsed_event.event_id)
        return {
            "status": "duplicate_ignored",
            "event_id": parsed_event.event_id,
        }

    return {
        "status": "accepted",
        "event_id": parsed_event.event_id,
        "correlation_id": correlation_id,
    }

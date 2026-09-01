"""Razorpay webhook gateway schema — Block 2.

Creates the durable razorpay_webhook_events inbox table and adds
external Razorpay identifiers to orders and payments.

Revision ID: 002
Revises: 001
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # razorpay_webhook_events
    # ------------------------------------------------------------------
    op.create_table(
        "razorpay_webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("razorpay_event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("signature", sa.String(128), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "processing_status",
            sa.String(32),
            server_default="RECEIVED",
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.UniqueConstraint("razorpay_event_id", name="uq_webhook_razorpay_event_id"),
    )
    op.create_index(
        "ix_webhook_events_status", "razorpay_webhook_events", ["processing_status"]
    )
    op.create_index(
        "ix_webhook_events_type", "razorpay_webhook_events", ["event_type"]
    )
    op.create_index(
        "ix_webhook_events_correlation", "razorpay_webhook_events", ["correlation_id"]
    )

    # ------------------------------------------------------------------
    # external IDs on orders & payments
    # ------------------------------------------------------------------
    op.add_column(
        "orders",
        sa.Column("razorpay_order_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_orders_razorpay_order_id", "orders", ["razorpay_order_id"])

    op.add_column(
        "payments",
        sa.Column("razorpay_payment_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_payments_razorpay_payment_id", "payments", ["razorpay_payment_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_payments_razorpay_payment_id", table_name="payments")
    op.drop_column("payments", "razorpay_payment_id")

    op.drop_index("ix_orders_razorpay_order_id", table_name="orders")
    op.drop_column("orders", "razorpay_order_id")

    op.drop_index("ix_webhook_events_correlation", table_name="razorpay_webhook_events")
    op.drop_index("ix_webhook_events_type", table_name="razorpay_webhook_events")
    op.drop_index("ix_webhook_events_status", table_name="razorpay_webhook_events")
    op.drop_table("razorpay_webhook_events")

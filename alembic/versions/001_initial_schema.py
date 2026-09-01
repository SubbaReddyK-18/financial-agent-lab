"""Initial schema — Financial Agent Lab Block 1.

Creates all tables for the financial core and recovery domain.

Revision ID: 001
Revises:
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # merchants
    # ------------------------------------------------------------------
    op.create_table(
        "merchants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ------------------------------------------------------------------
    # customers
    # ------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"],
                                ondelete="RESTRICT", name="fk_customer_merchant"),
        sa.UniqueConstraint("merchant_id", "external_reference",
                            name="uq_customer_merchant_extref"),
    )
    op.create_index("ix_customers_merchant_id", "customers", ["merchant_id"])

    # ------------------------------------------------------------------
    # orders
    # ------------------------------------------------------------------
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"],
                                ondelete="RESTRICT", name="fk_order_merchant"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"],
                                ondelete="RESTRICT", name="fk_order_customer"),
    )
    op.create_index("ix_orders_merchant_id", "orders", ["merchant_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])

    # ------------------------------------------------------------------
    # payments
    # ------------------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("payment_method", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"],
                                ondelete="RESTRICT", name="fk_payment_order"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"],
                                ondelete="RESTRICT", name="fk_payment_customer"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_customer_id", "payments", ["customer_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    # ------------------------------------------------------------------
    # payment_attempts
    # ------------------------------------------------------------------
    op.create_table(
        "payment_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"],
                                ondelete="RESTRICT", name="fk_attempt_payment"),
        sa.UniqueConstraint("payment_id", "attempt_number",
                            name="uq_attempt_payment_number"),
    )
    op.create_index("ix_payment_attempts_payment_id", "payment_attempts", ["payment_id"])

    # ------------------------------------------------------------------
    # merchant_recovery_policies
    # ------------------------------------------------------------------
    op.create_table(
        "merchant_recovery_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("maximum_discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximum_interventions", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("cooldown_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("high_value_threshold_minor", sa.BigInteger(), nullable=True),
        sa.Column("high_value_requires_approval", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("low_confidence_requires_review", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"],
                                ondelete="RESTRICT", name="fk_policy_merchant"),
        sa.UniqueConstraint("merchant_id", name="uq_policy_merchant"),
    )

    # ------------------------------------------------------------------
    # recovery_cases
    # ------------------------------------------------------------------
    op.create_table(
        "recovery_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_at_risk_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"],
                                ondelete="RESTRICT", name="fk_case_merchant"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"],
                                ondelete="RESTRICT", name="fk_case_customer"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"],
                                ondelete="RESTRICT", name="fk_case_payment"),
    )
    op.create_index("ix_recovery_cases_merchant_id", "recovery_cases", ["merchant_id"])
    op.create_index("ix_recovery_cases_customer_id", "recovery_cases", ["customer_id"])
    op.create_index("ix_recovery_cases_payment_id", "recovery_cases", ["payment_id"])
    op.create_index("ix_recovery_cases_status", "recovery_cases", ["status"])

    # ------------------------------------------------------------------
    # recovery_actions
    # ------------------------------------------------------------------
    op.create_table(
        "recovery_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PROPOSED"),
        sa.Column("discount_percent_offered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["recovery_case_id"], ["recovery_cases.id"],
                                ondelete="RESTRICT", name="fk_action_case"),
    )
    op.create_index("ix_recovery_actions_case_id", "recovery_actions", ["recovery_case_id"])

    # ------------------------------------------------------------------
    # financial_events  (append-only, FS-07)
    # ------------------------------------------------------------------
    op.create_table(
        "financial_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_financial_events_aggregate", "financial_events",
                    ["aggregate_type", "aggregate_id"])
    op.create_index("ix_financial_events_type", "financial_events", ["event_type"])
    op.create_index("ix_financial_events_correlation", "financial_events", ["correlation_id"])


def downgrade() -> None:
    # Drop in reverse dependency order.
    op.drop_table("financial_events")
    op.drop_table("recovery_actions")
    op.drop_table("recovery_cases")
    op.drop_table("merchant_recovery_policies")
    op.drop_table("payment_attempts")
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("customers")
    op.drop_table("merchants")

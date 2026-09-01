"""Enforce internal amount authority and core financial persistence invariants.

Revision ID: 009
Revises: 008
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A Razorpay identifier identifies at most one pre-existing internal record.
    # The partial form permits ordinary internal records before gateway binding.
    op.drop_index("ix_orders_razorpay_order_id", table_name="orders")
    op.create_index(
        "uq_orders_razorpay_order_id",
        "orders",
        ["razorpay_order_id"],
        unique=True,
        postgresql_where=sa.text("razorpay_order_id IS NOT NULL"),
    )
    op.drop_index("ix_payments_razorpay_payment_id", table_name="payments")
    op.create_index(
        "uq_payments_razorpay_payment_id",
        "payments",
        ["razorpay_payment_id"],
        unique=True,
        postgresql_where=sa.text("razorpay_payment_id IS NOT NULL"),
    )

    op.create_check_constraint(
        "ck_orders_amount_minor_positive", "orders", "amount_minor > 0"
    )
    op.create_check_constraint(
        "ck_payments_amount_minor_positive", "payments", "amount_minor > 0"
    )
    op.create_check_constraint(
        "ck_recovery_cases_amount_at_risk_positive",
        "recovery_cases",
        "amount_at_risk_minor > 0",
    )
    op.create_index(
        "uq_recovery_cases_active_payment",
        "recovery_cases",
        ["payment_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('OPEN', 'IN_PROGRESS')"),
    )

    # A request is retried in place. A case must not acquire a second durable
    # decision request merely because workers race or restart.
    op.create_unique_constraint(
        "uq_recovery_decision_request_case",
        "recovery_decision_requests",
        ["recovery_case_id"],
    )
    op.create_check_constraint(
        "ck_decision_request_attempt_count_nonnegative",
        "recovery_decision_requests",
        "attempt_count >= 0",
    )
    op.create_check_constraint(
        "ck_decision_request_max_attempts_positive",
        "recovery_decision_requests",
        "max_attempts >= 1",
    )
    op.create_check_constraint(
        "ck_decision_request_attempt_count_bounded",
        "recovery_decision_requests",
        "attempt_count <= max_attempts",
    )

    # Financial events are append-only facts. Corrections must be represented
    # as new events, never mutation or deletion of a persisted event.
    op.execute(
        """
        CREATE FUNCTION prevent_financial_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'financial_events are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_financial_events_append_only
        BEFORE UPDATE OR DELETE ON financial_events
        FOR EACH ROW EXECUTE FUNCTION prevent_financial_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_financial_events_append_only ON financial_events")
    op.execute("DROP FUNCTION prevent_financial_event_mutation()")
    for name in (
        "ck_decision_request_attempt_count_bounded",
        "ck_decision_request_max_attempts_positive",
        "ck_decision_request_attempt_count_nonnegative",
    ):
        op.drop_constraint(name, "recovery_decision_requests", type_="check")
    op.drop_constraint(
        "uq_recovery_decision_request_case",
        "recovery_decision_requests",
        type_="unique",
    )
    op.drop_index("uq_recovery_cases_active_payment", table_name="recovery_cases")
    op.drop_constraint(
        "ck_recovery_cases_amount_at_risk_positive",
        "recovery_cases",
        type_="check",
    )
    op.drop_constraint("ck_payments_amount_minor_positive", "payments", type_="check")
    op.drop_constraint("ck_orders_amount_minor_positive", "orders", type_="check")
    op.drop_index("uq_payments_razorpay_payment_id", table_name="payments")
    op.create_index("ix_payments_razorpay_payment_id", "payments", ["razorpay_payment_id"])
    op.drop_index("uq_orders_razorpay_order_id", table_name="orders")
    op.create_index("ix_orders_razorpay_order_id", "orders", ["razorpay_order_id"])

"""
infrastructure/database/orm/__init__.py

Import all ORM models here so SQLAlchemy's metadata registry is populated
before Alembic inspects it for autogenerate or migration runs.
"""

from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.approval import RecoveryActionApprovalORM
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.decision_request import RecoveryDecisionRequestORM
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.merchant import MerchantORM
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
from infrastructure.database.orm.payment import OrderORM, PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import (
    MerchantRecoveryPolicyORM,
    RecoveryActionORM,
    RecoveryCaseORM,
)
from infrastructure.database.orm.simulation import SimulationRunORM
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM

__all__ = [
    "MerchantORM",
    "CustomerORM",
    "RecoveryDecisionRequestORM",
    "OrderORM",
    "PaymentORM",
    "PaymentAttemptORM",
    "MerchantRecoveryPolicyORM",
    "RecoveryCaseORM",
    "RecoveryActionORM",
    "RecoveryOutboxEventORM",
    "FinancialEventORM",
    "RazorpayWebhookEventORM",
    "SimulationRunORM",
    "AIDecisionRecordORM",
    "RecoveryActionApprovalORM",
]

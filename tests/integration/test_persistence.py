"""
tests/integration/test_persistence.py

Integration tests for database persistence and relationships.

These tests require a live PostgreSQL database.
Run with: pytest -m integration

Reuses the shared application settings (get_settings().async_database_url).

Tests verify: table creation, CRUD, FK constraints, unique constraints,
and amount integrity (BigInteger, no float).
"""

import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.settings import get_settings
from infrastructure.database.base import Base
import infrastructure.database.orm  # noqa: F401 — register all models
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.merchant import MerchantORM
from infrastructure.database.orm.payment import OrderORM, PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import (
    MerchantRecoveryPolicyORM,
    RecoveryActionORM,
    RecoveryCaseORM,
)


def _test_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return get_settings().async_database_url


@pytest_asyncio.fixture
async def engine():
    url = _test_db_url()
    engine = create_async_engine(url, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


pytestmark = pytest.mark.integration


class TestMerchantPersistence:
    async def test_create_and_retrieve_merchant(self, db: AsyncSession):
        merchant = MerchantORM(
            id=uuid.uuid4(),
            name="Test Merchant",
            currency="INR",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(merchant)
        await db.flush()

        retrieved = await db.get(MerchantORM, merchant.id)
        assert retrieved is not None
        assert retrieved.name == "Test Merchant"
        assert retrieved.currency == "INR"


class TestCustomerPersistence:
    async def test_create_customer_with_merchant(self, db: AsyncSession):
        merchant = MerchantORM(
            id=uuid.uuid4(), name="M2", currency="INR",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(merchant)
        await db.flush()

        customer = CustomerORM(
            id=uuid.uuid4(),
            merchant_id=merchant.id,
            external_reference="C-001",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(customer)
        await db.flush()

        retrieved = await db.get(CustomerORM, customer.id)
        assert retrieved is not None
        assert retrieved.merchant_id == merchant.id


class TestPaymentPersistence:
    async def test_payment_amount_stored_as_bigint(self, db: AsyncSession):
        """Verify monetary amounts survive DB round-trip without precision loss."""
        amount_paise = 500000  # ₹5,000.00

        merchant = MerchantORM(
            id=uuid.uuid4(), name="M3", currency="INR",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(merchant)
        await db.flush()

        customer = CustomerORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(customer)
        await db.flush()

        order = OrderORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            customer_id=customer.id, amount_minor=amount_paise,
            currency="INR", status="CREATED",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(order)
        await db.flush()

        payment = PaymentORM(
            id=uuid.uuid4(), order_id=order.id,
            customer_id=customer.id, amount_minor=amount_paise,
            currency="INR", status="FAILED",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(payment)
        await db.flush()

        retrieved = await db.get(PaymentORM, payment.id)
        assert retrieved is not None
        # Amount must be exactly preserved — no float precision loss.
        assert retrieved.amount_minor == amount_paise
        assert isinstance(retrieved.amount_minor, int)

    async def test_payment_attempt_unique_constraint(self, db: AsyncSession):
        """(payment_id, attempt_number) must be unique."""
        from sqlalchemy.exc import IntegrityError

        merchant = MerchantORM(
            id=uuid.uuid4(), name="M4", currency="INR",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(merchant)
        await db.flush()

        customer = CustomerORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(customer)
        await db.flush()

        order = OrderORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            customer_id=customer.id, amount_minor=100000,
            currency="INR", status="CREATED",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(order)
        await db.flush()

        payment = PaymentORM(
            id=uuid.uuid4(), order_id=order.id,
            customer_id=customer.id, amount_minor=100000,
            currency="INR", status="CREATED",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(payment)
        await db.flush()

        attempt1 = PaymentAttemptORM(
            id=uuid.uuid4(), payment_id=payment.id,
            attempt_number=1, status="PENDING",
            attempted_at=datetime.now(tz=timezone.utc),
        )
        db.add(attempt1)
        await db.flush()

        attempt2_duplicate = PaymentAttemptORM(
            id=uuid.uuid4(), payment_id=payment.id,
            attempt_number=1,   # DUPLICATE — must fail
            status="PENDING",
            attempted_at=datetime.now(tz=timezone.utc),
        )
        db.add(attempt2_duplicate)
        with pytest.raises(IntegrityError):
            await db.flush()


class TestRecoveryPersistence:
    async def test_recovery_case_references_payment(self, db: AsyncSession):
        merchant = MerchantORM(
            id=uuid.uuid4(), name="M5", currency="INR",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(merchant)
        await db.flush()

        customer = CustomerORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(customer)
        await db.flush()

        order = OrderORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            customer_id=customer.id, amount_minor=200000,
            currency="INR", status="CREATED",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(order)
        await db.flush()

        payment = PaymentORM(
            id=uuid.uuid4(), order_id=order.id,
            customer_id=customer.id, amount_minor=200000,
            currency="INR", status="FAILED",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(payment)
        await db.flush()

        case = RecoveryCaseORM(
            id=uuid.uuid4(),
            merchant_id=merchant.id,
            customer_id=customer.id,
            payment_id=payment.id,
            amount_at_risk_minor=200000,
            status="OPEN",
            opened_at=datetime.now(tz=timezone.utc),
        )
        db.add(case)
        await db.flush()

        retrieved = await db.get(RecoveryCaseORM, case.id)
        assert retrieved is not None
        assert retrieved.payment_id == payment.id
        assert retrieved.amount_at_risk_minor == 200000

    async def test_one_policy_per_merchant_constraint(self, db: AsyncSession):
        from sqlalchemy.exc import IntegrityError

        merchant = MerchantORM(
            id=uuid.uuid4(), name="M6", currency="INR",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(merchant)
        await db.flush()

        p1 = MerchantRecoveryPolicyORM(
            id=uuid.uuid4(), merchant_id=merchant.id,
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(p1)
        await db.flush()

        p2 = MerchantRecoveryPolicyORM(
            id=uuid.uuid4(), merchant_id=merchant.id,  # DUPLICATE merchant
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
        db.add(p2)
        with pytest.raises(IntegrityError):
            await db.flush()

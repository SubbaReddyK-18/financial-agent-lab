"""
tests/integration/test_ai_benchmark.py

Integration tests for AI Decision and Benchmark endpoints against live PostgreSQL.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.main import app
from apps.api.settings import get_settings
from infrastructure.database.orm.ai import AIDecisionRecordORM

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    url = get_settings().async_database_url
    engine = create_async_engine(url, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestAIApiEndpoints:
    async def test_single_ai_decision_endpoint_persists_audit_record(
        self, client: AsyncClient, db: AsyncSession
    ):
        req_payload = {
            "amount_minor": 250000,  # ₹2,500.00
            "currency": "INR",
            "payment_method": "UPI",
            "failure_code": "GATEWAY_TIMEOUT",
            "attempt_count": 1,
            "customer_historical_success_rate": 0.88,
            "customer_segment": "VIP",
            "scenario_id": "test_ai_scenario_001",
        }

        response = await client.post("/ai/decide", json=req_payload)
        assert response.status_code == 200
        data = response.json()

        assert "decision_id" in data
        assert data["recommended_action"] in ["RETRY", "PAYMENT_LINK", "WAIT", "NOTIFY", "ESCALATE"]
        assert data["confidence"] > 0
        assert data["fallback_used"] is False

        # Verify audit persistence in PostgreSQL
        record = await db.scalar(
            select(AIDecisionRecordORM).where(
                AIDecisionRecordORM.scenario_id == "test_ai_scenario_001"
            )
        )
        assert record is not None
        assert record.recommended_action == data["recommended_action"]
        assert record.input_tokens > 0

    async def test_ai_benchmark_endpoint(self, client: AsyncClient):
        response = await client.post(
            "/ai/benchmark",
            json={"scenario_count": 30, "seed": 42},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["scenario_count"] == 30
        assert data["economic_value_capture_ratio"] >= 0.0
        assert "ai_oracle_agreement_rate" in data
        assert "net_ai_economic_value_minor" in data

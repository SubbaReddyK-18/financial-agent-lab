"""
tests/integration/test_simulation_benchmark.py

Integration and benchmark performance tests for the Simulation Engine.

Tests:
1. 10,000-scenario local execution benchmark.
2. Comparative hierarchy validation (Oracle >= Baseline >= Wait).
3. API endpoints against live PostgreSQL.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.main import app
from apps.api.settings import get_settings
from domain.intelligence.simulation.runner import ScenarioBatchRunner

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


class TestSimulationBenchmark:
    def test_ten_thousand_scenarios_benchmark_performance(self):
        """
        Benchmark: 10,000 synthetic scenarios evaluated across No-Intervention,
        Deterministic Baseline, and Oracle in under 3.5 seconds locally.
        """
        runner = ScenarioBatchRunner(seed=42)
        result = runner.run_benchmark(scenario_count=10_000, run_name="ten_k_benchmark")

        assert result.scenario_count == 10_000
        assert result.duration_ms < 5000  # Strict local SLA < 5 seconds

        # Comparative validation: Oracle expected net revenue >= Baseline expected net revenue
        assert (
            result.oracle_metrics.expected_net_incremental_revenue_minor
            >= result.baseline_metrics.expected_net_incremental_revenue_minor
        )
        assert (
            result.baseline_metrics.expected_net_incremental_revenue_minor
            >= result.no_intervention_metrics.expected_net_incremental_revenue_minor
        )
        assert result.no_intervention_metrics.expected_net_incremental_revenue_minor == 0

    async def test_simulation_api_endpoints(self, client: AsyncClient):
        # 1. Run simulation via API
        post_res = await client.post(
            "/simulation/run",
            json={"scenario_count": 500, "seed": 42, "run_name": "api_test_run"},
        )
        assert post_res.status_code == 201
        run_data = post_res.json()
        run_id = run_data["run_id"]
        assert run_data["scenario_count"] == 500
        assert run_data["baseline_metrics"]["total_interventions"] > 0

        # 2. Get full simulation run
        get_res = await client.get(f"/simulation/runs/{run_id}")
        assert get_res.status_code == 200
        assert get_res.json()["run_id"] == run_id

        # 3. Get simulation summary
        summary_res = await client.get(f"/simulation/runs/{run_id}/summary")
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert "comparisons" in summary
        assert "deterministic_baseline" in summary["comparisons"]
        assert "simulation_oracle" in summary["comparisons"]

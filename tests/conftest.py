"""
tests/conftest.py

Shared pytest fixtures for the Financial Agent Lab test suite.

Unit tests (marked @pytest.mark.unit) run without any I/O.
Integration tests (marked @pytest.mark.integration) require a live database.
"""

import pytest

from apps.api.settings import get_settings


@pytest.fixture(autouse=True)
def force_mock_llm_for_tests(monkeypatch):
    """
    Ensure the automated test suite always uses MockLLMClient (Requirement 13)
    and NEVER consumes live Gemini/OpenAI API quota during tests.
    """
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

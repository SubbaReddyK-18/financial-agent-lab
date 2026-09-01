"""
domain/intelligence/interfaces.py

Abstract interface for RecoveryDecisionProvider.

ARCHITECTURAL PRINCIPLE (Block 3, Step 12):
Defines the clean conceptual interface that both the DeterministicBaselineDecisionProvider
and future AI Agents (Block 4) implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.intelligence.models.action_economics import RecoveryDecisionRecommendation
from domain.intelligence.models.context import RecoveryContext


class RecoveryDecisionProvider(ABC):
    """
    Abstract contract for any recovery decision engine (Baseline, Oracle, AI Agent).
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable identifier of the decision provider."""
        ...

    @abstractmethod
    def evaluate_decision(
        self,
        context: RecoveryContext,
        scenario_id: str | None = None,
    ) -> RecoveryDecisionRecommendation:
        """
        Evaluate the recovery context and return a structured decision recommendation.
        """
        ...

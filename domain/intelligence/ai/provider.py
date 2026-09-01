"""
domain/intelligence/ai/provider.py

AIDecisionProvider implementing the RecoveryDecisionProvider interface with
deterministic schema validation, policy controls, and baseline fallback.

ARCHITECTURAL PRINCIPLES (Block 4, Part 1, 5, 7, 8, 9, 10):
1. AI Proposes -> Deterministic Systems Control.
2. Strict schema parsing rejects malformed output without silent corruption.
3. Fallback to DeterministicBaselineDecisionProvider upon any AI exception or invalid output.
4. Calculates inference cost in minor units (paise).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from apps.api.settings import Settings, get_settings
from domain.intelligence.ai.models import AIDecisionProposal, AIDecisionRecord, AIRecoveryContext
from domain.intelligence.ai.prompt import RecoveryPromptBuilder
from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.economic_engine import evaluate_all_candidate_actions
from domain.intelligence.interfaces import RecoveryDecisionProvider
from domain.intelligence.models.action_economics import (
    ActionEconomicParameters,
    RecoveryDecisionRecommendation,
)
from domain.intelligence.models.context import RecoveryContext
from domain.policies.validator import validate_action_against_policy
from domain.shared.enums import RecoveryActionType
from infrastructure.ai.client import LLMClient, LLMResponse, MockLLMClient, create_llm_client

logger = logging.getLogger("domain.intelligence.ai.provider")


class AIDecisionProvider(RecoveryDecisionProvider):
    """
    AI-assisted recovery decision provider with deterministic control and fallback.
    """

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        settings: Optional[Settings] = None,
        provider_name: str = "AIAssistedRecoveryAgent",
    ):
        self._settings = settings or get_settings()
        self._client = client or create_llm_client(self._settings)
        self._provider_name = provider_name
        self._baseline_fallback = DeterministicBaselineDecisionProvider()
        self.last_decision_record: Optional[AIDecisionRecord] = None

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _calculate_inference_cost_minor(self, input_tokens: int, output_tokens: int) -> int:
        """Estimate LLM inference cost in paise."""
        input_usd = (input_tokens / 1_000_000.0) * self._settings.ai_cost_per_million_input_tokens_usd
        output_usd = (output_tokens / 1_000_000.0) * self._settings.ai_cost_per_million_output_tokens_usd
        total_usd = input_usd + output_usd
        total_inr = total_usd * self._settings.usd_to_inr_rate
        return int(round(total_inr * 100))  # Convert INR to paise

    async def evaluate_decision_async(
        self,
        context: RecoveryContext,
        scenario_id: Optional[str] = None,
    ) -> RecoveryDecisionRecommendation:
        """Async decision evaluation pipeline."""
        decision_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)
        prompt_version = RecoveryPromptBuilder.version

        # 1. Sanitize context (Strict Observability Boundary)
        ai_ctx = AIRecoveryContext.from_recovery_context(context)
        system_prompt = RecoveryPromptBuilder.get_system_prompt()
        user_prompt = RecoveryPromptBuilder.build_user_prompt(ai_ctx)

        raw_proposal: Optional[AIDecisionProposal] = None
        proposal_policy_result = None
        fallback_used = False
        fallback_reason: Optional[str] = None
        llm_resp = LLMResponse(content="", input_tokens=0, output_tokens=0, latency_ms=0.0)

        # 2. Invoke LLM Client with Exception Handling
        try:
            llm_resp = await self._client.complete(system_prompt, user_prompt)
            proposal_dict = json.loads(llm_resp.content)
            raw_proposal = AIDecisionProposal.model_validate(proposal_dict)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("AI structured schema validation failed: %s", e)
            fallback_used = True
            fallback_reason = f"Schema validation error: {e}"
        except Exception as e:
            logger.warning("AI provider call failed: %s", e)
            fallback_used = True
            fallback_reason = f"Provider exception: {e}"

        # 3. Policy & Economic Validation of AI Proposal
        if not fallback_used and raw_proposal is not None:
            if raw_proposal.recommended_action != RecoveryActionType.WAIT:
                # Policy Gate Check for active interventions
                policy_check = validate_action_against_policy(
                    policy=context.policy,
                    action_type=raw_proposal.recommended_action,
                    payment_amount_minor=context.amount_minor,
                    completed_interventions=context.completed_interventions,
                    last_action_at=context.last_action_at,
                    requested_discount_percent=raw_proposal.recommended_discount_percent,
                    now=now,
                )
                proposal_policy_result = policy_check

                if not policy_check.is_valid:
                    logger.warning(
                        "AI proposal %s rejected by merchant policy: %s",
                        raw_proposal.recommended_action.value,
                        policy_check.violations,
                    )
                    fallback_used = True
                    fallback_reason = f"Policy violation: {'; '.join(policy_check.violations)}"

        # 4. Construct Recommendation (AI or Deterministic Fallback)
        if fallback_used or raw_proposal is None:
            # Execute Baseline Fallback
            baseline_rec = self._baseline_fallback.evaluate_decision(context, scenario_id)
            final_action = baseline_rec.recommended_action
            final_discount = baseline_rec.recommended_discount_percent
            final_net = baseline_rec.expected_net_incremental_revenue_minor
            final_rec = baseline_rec
            confidence = 0.50
            reasoning_codes = ["DETERMINISTIC_BASELINE_FALLBACK"]
            uncertainty = "HIGH"
            requires_human_review = True
        else:
            # Evaluate Candidate Actions via Deterministic Economic Engine
            candidate_economics = {
                RecoveryActionType.WAIT: ActionEconomicParameters(
                    action_type=RecoveryActionType.WAIT,
                    intervention_cost_minor=0,
                    estimated_success_probability=raw_proposal.estimated_natural_recovery_probability or 0.20,
                ),
                RecoveryActionType.RETRY: ActionEconomicParameters(
                    action_type=RecoveryActionType.RETRY,
                    intervention_cost_minor=20,
                    estimated_success_probability=raw_proposal.estimated_action_success_probability if raw_proposal.recommended_action == RecoveryActionType.RETRY else 0.55,
                ),
                RecoveryActionType.PAYMENT_LINK: ActionEconomicParameters(
                    action_type=RecoveryActionType.PAYMENT_LINK,
                    intervention_cost_minor=50,
                    estimated_success_probability=raw_proposal.estimated_action_success_probability if raw_proposal.recommended_action == RecoveryActionType.PAYMENT_LINK else 0.45,
                    discount_percent_offered=raw_proposal.recommended_discount_percent,
                ),
                RecoveryActionType.NOTIFY: ActionEconomicParameters(
                    action_type=RecoveryActionType.NOTIFY,
                    intervention_cost_minor=15,
                    estimated_success_probability=raw_proposal.estimated_action_success_probability if raw_proposal.recommended_action == RecoveryActionType.NOTIFY else 0.35,
                ),
                RecoveryActionType.ESCALATE: ActionEconomicParameters(
                    action_type=RecoveryActionType.ESCALATE,
                    intervention_cost_minor=500,
                    estimated_success_probability=raw_proposal.estimated_action_success_probability if raw_proposal.recommended_action == RecoveryActionType.ESCALATE else 0.60,
                ),
            }

            nat_prob = raw_proposal.estimated_natural_recovery_probability or 0.20
            rec = evaluate_all_candidate_actions(
                context=context,
                candidate_economics=candidate_economics,
                natural_recovery_probability=nat_prob,
                scenario_id=scenario_id,
                now=now,
            )

            chosen_eval = rec.get_evaluation(raw_proposal.recommended_action)
            chosen_net = chosen_eval.expected_net_incremental_revenue_minor if chosen_eval else 0

            # The proposal remains auditable, but executable selection is the
            # deterministic policy/economic result, never raw LLM authority.
            final_action = rec.policy_permitted_action
            final_eval = rec.get_evaluation(final_action)
            final_rec = RecoveryDecisionRecommendation(
                decision_id=decision_id,
                scenario_id=scenario_id,
                context=context,
                candidate_evaluations=rec.candidate_evaluations,
                economically_optimal_action=rec.economically_optimal_action,
                economically_optimal_net_revenue_minor=rec.economically_optimal_net_revenue_minor,
                policy_permitted_action=rec.policy_permitted_action,
                policy_permitted_net_revenue_minor=rec.policy_permitted_net_revenue_minor,
                recommended_action=final_action,
                recommended_discount_percent=final_eval.discount_percent_offered if final_eval else 0,
                expected_net_incremental_revenue_minor=final_eval.expected_net_incremental_revenue_minor if final_eval else 0,
                is_policy_override=(final_action != raw_proposal.recommended_action),
                evaluation_timestamp=now,
            )

            confidence = raw_proposal.confidence
            reasoning_codes = raw_proposal.reasoning_codes
            uncertainty = raw_proposal.uncertainty
            requires_human_review = raw_proposal.requires_human_review

        # 5. Calculate Cost and Record
        llm_cost_minor = self._calculate_inference_cost_minor(llm_resp.input_tokens, llm_resp.output_tokens)
        record = AIDecisionRecord(
            decision_id=decision_id,
            scenario_id=scenario_id,
            provider=self.provider_name,
            model=self._settings.ai_model,
            prompt_version=prompt_version,
            prompt_hash=RecoveryPromptBuilder.content_hash,
            agent_version=RecoveryPromptBuilder.bundle_version,
            raw_proposal=raw_proposal,
            proposal_policy_result=proposal_policy_result,
            recommended_action=final_action,
            confidence=confidence,
            reasoning_codes=reasoning_codes,
            uncertainty=uncertainty,
            requires_human_review=requires_human_review,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            latency_ms=llm_resp.latency_ms,
            input_tokens=llm_resp.input_tokens,
            output_tokens=llm_resp.output_tokens,
            estimated_llm_cost_minor=llm_cost_minor,
            final_recommendation=final_rec,
            created_at=now,
        )
        self.last_decision_record = record
        return final_rec

    def evaluate_decision(
        self,
        context: RecoveryContext,
        scenario_id: Optional[str] = None,
    ) -> RecoveryDecisionRecommendation:
        """Synchronous wrapper for evaluate_decision_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In an already running event loop (e.g. within an async test or endpoint)
            # Run in a new task or nest via thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(self.evaluate_decision_async(context, scenario_id)))
                return future.result()
        else:
            return asyncio.run(self.evaluate_decision_async(context, scenario_id))

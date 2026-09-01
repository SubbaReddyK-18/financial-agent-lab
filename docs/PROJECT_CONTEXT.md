# `PROJECT_CONTEXT.md`

> **Purpose of this document:** This is the authoritative project-context document for **Financial Agent Lab** as development moves from Antigravity to OpenAI Codex. It is intended to be placed inside the repository and treated as persistent architectural context for all future implementation work.
>
> **Important status rule:** This document deliberately distinguishes between what was implemented, what was intended, what is partially wired, and what still requires verification. Previous block completion reports are historical evidence, not absolute proof of current runtime behavior. **The actual repository code is the final authority on implementation status.**

---

# 1. Project Identity

## 1.1 Project Name

**Financial Agent Lab**

## 1.2 Project Type

Financial Agent Lab is a Python/FastAPI/PostgreSQL system designed as an AI-assisted **payment recovery decision and execution prototype**.

The project is being developed in the context of a **Razorpay AI Buildathon** and is intended to demonstrate how an AI-driven recovery system can make economically informed decisions after payment failures while maintaining strict financial, policy, execution, security, and audit boundaries.

This is **not merely a payment gateway integration**.

The central problem is what should happen **after a payment failure**.

A failed payment does not necessarily mean that the merchant has permanently lost the transaction. Depending on the failure reason, customer behavior, payment history, timing, merchant policy, intervention cost, and expected probability of recovery, different recovery strategies may have very different economic outcomes.

The system therefore attempts to answer:

> **Given a failed payment and the available observable context, should the merchant intervene, and if so, which recovery action produces the best expected economic outcome while respecting merchant policy and financial safety constraints?**

The system uses AI as one component of that decision process, but AI is deliberately **not the final authority**.

---

# 2. Project Aim

The overall aim of Financial Agent Lab is to build a **financially safe, economically aware, AI-assisted payment recovery decision system**.

The system should transform a failed-payment event into a structured recovery opportunity.

Instead of treating every failed payment identically, the system should reason about:

* whether natural recovery is likely;
* whether intervention is worthwhile;
* what intervention is appropriate;
* whether the intervention complies with merchant policy;
* what the expected recovery value is;
* what the intervention costs;
* what the expected incremental value is compared with doing nothing;
* whether the action is safe to execute;
* whether the action has become stale or obsolete;
* whether it has already been executed;
* and how the eventual result can be audited.

The key optimization objective is **not simply recovery rate**.

A strategy that increases the number of recovered payments but gives away excessive discounts, incurs unnecessary intervention costs, or intervenes when natural recovery was already likely may be economically inferior.

The system therefore focuses on **expected economic value**, especially expected net incremental recovery value.

---

# 3. Core Problem

The basic business scenario is:

```text
Customer attempts payment
        ↓
Payment fails
        ↓
Merchant has an opportunity to recover the payment
        ↓
System evaluates whether intervention is worthwhile
        ↓
System selects a possible recovery action
        ↓
Action is constrained by deterministic merchant policy
        ↓
EconomicEngine evaluates financial consequences
        ↓
Control Plane governs execution
        ↓
Outcome is recorded and observable
```

Possible recovery actions currently include:

* `WAIT`
* `RETRY`
* `PAYMENT_LINK`
* `NOTIFY`
* `ESCALATE`

The system must avoid the simplistic assumption:

> "A payment failed, therefore send a payment link."

Instead, it should determine whether intervention creates sufficient expected incremental value.

---

# 4. What Makes This Different From a Payment Gateway

A payment gateway primarily facilitates payment processing.

Financial Agent Lab sits around the **recovery decision problem**.

The distinction is:

### Payment processing

Answers:

> Can the payment be initiated, authorized, captured, refunded, etc.?

### Payment recovery

Answers:

> After a failed payment, what should the merchant do next?

### AI decision support

Answers:

> Based on the observable context, what recovery action appears promising?

### Policy enforcement

Answers:

> Is the proposed action actually permitted?

### Economic optimization

Answers:

> What is the expected financial value of each permitted action?

### Execution

Answers:

> How should the approved action be safely dispatched, retried, deduplicated, or superseded?

### Reconciliation

Answers:

> What actually happened to the payment according to the authoritative payment event source?

These responsibilities must remain separate.

---

# 5. Primary Objectives

Financial Agent Lab has the following major objectives.

## 5.1 Financial Recovery

Recover failed payments where recovery is economically and operationally justified.

## 5.2 Economic Optimization

Optimize expected economic value rather than blindly maximizing raw recovery probability.

## 5.3 AI-Assisted Decision Making

Use an LLM to generate structured recovery proposals based on observable payment/customer/context information.

## 5.4 Deterministic Policy Enforcement

Never allow an AI proposal to bypass merchant-defined constraints.

## 5.5 Financial Safety

Prevent AI or recovery execution code from directly becoming authoritative over payment capture or financial state.

## 5.6 Payment-State Integrity

Payment state must be derived through the authoritative webhook/reconciliation pathway.

## 5.7 Observability

Make decisions, actions, outcomes, retries, and economic metrics inspectable.

## 5.8 Auditability

Provide a trace explaining how a recovery decision progressed from context to proposal to policy to action to execution.

## 5.9 Idempotency

Prevent duplicate processing and duplicate action execution.

## 5.10 Concurrency Safety

Use PostgreSQL transactions and row-level locking where required.

## 5.11 Transactional Consistency

Ensure logically related durable records are persisted atomically.

## 5.12 Production Resilience

Handle crashes, stale actions, abandoned outbox events, retries, shutdowns, configuration errors, and malformed requests safely.

## 5.13 Security

Protect webhooks, administrative endpoints, secrets, logs, and error responses.

## 5.14 Simulation and Evaluation

Provide a synthetic environment in which AI strategies can be compared against deterministic baselines and an oracle without exposing synthetic ground truth to production decision paths.

## 5.15 Extensibility

The architecture should allow additional recovery strategies, providers, policies, evaluation mechanisms, and real execution adapters without collapsing authority boundaries.

---

# 6. Fundamental Architectural Philosophy

The most important principle in the entire system is:

> **The goal is not to build an AI that controls payments.**

The goal is to build:

> **a financially safe, deterministic recovery decision system in which AI is one bounded component inside a larger authoritative architecture.**

The conceptual authority hierarchy is:

```text
Razorpay
   ↓
authoritative payment events

PostgreSQL
   ↓
durable transactional source of truth

Webhook reconciliation
   ↓
payment-state authority

Recovery Case
   ↓
represents the recoverable business problem

AI
   ↓
proposes possible actions

Merchant Policy
   ↓
deterministically constrains proposals

EconomicEngine
   ↓
determines financial valuation

Orchestrator
   ↓
coordinates decision creation

Control Plane
   ↓
governs action lifecycle and dispatch

Outbox
   ↓
provides durable dispatch intent

Executor
   ↓
performs the currently simulated action

Observability
   ↓
explains what happened

Simulation
   ↓
evaluates whether the strategy works
```

No lower-level component should silently acquire authority belonging to a higher-authority component.

---

# 7. Intended End-to-End Lifecycle

The intended business lifecycle is:

```text
Payment attempt
    ↓
Razorpay payment event
    ↓
Webhook authentication
    ↓
Durable webhook inbox
    ↓
Webhook processing
    ↓
Payment reconciliation
    ↓
Recovery case creation/resolution
    ↓
Recovery context construction
    ↓
AI proposal
    ↓
Schema validation
    ↓
Policy validation
    ↓
Economic evaluation
    ↓
Decision orchestration
    ↓
Recovery action
    ↓
Control Plane
    ↓
Transactional Outbox
    ↓
Action dispatch
    ↓
Test-mode executor
    ↓
Execution result
    ↓
Financial/audit records
    ↓
Observability
```

However, **the current implementation does not completely wire this lifecycle in the production runtime**.

In particular, the latest repository inspection found that webhook processing can create/reconcile recovery state but does not currently provide a production runtime call from webhook processing into:

```text
RecoveryDecisionOrchestrator.orchestrate_case()
```

Therefore Codex must distinguish the **intended lifecycle** above from the **currently wired runtime lifecycle**.

---

# 8. Current Implementation Status: Important Distinction

Previous block completion reports described Blocks 1–8 as completed.

A later repository inspection identified several discrepancies between those reports and actual runtime wiring.

These discrepancies are intentionally preserved here.

## Implemented

The repository contains substantial implementations for:

* domain financial models;
* recovery state machines;
* payment webhook verification;
* durable webhook inbox;
* reconciliation;
* simulation;
* economic evaluation;
* AI proposal generation;
* AI provider abstraction;
* recovery orchestration;
* recovery actions;
* observability;
* control plane;
* transactional outbox;
* API hardening;
* authentication;
* structured logging;
* correlation IDs;
* health/readiness;
* outbox worker;
* extensive unit and integration test suites.

## Partially wired

The following areas require careful repository inspection before being described as fully operational:

* webhook → decision orchestration;
* policy validation at every production action boundary;
* human approval semantics;
* outbox-exclusive dispatch;
* complete audit persistence;
* some database-level invariants.

## Known gaps

Known architectural gaps include:

1. webhook processing does not currently automatically invoke `orchestrate_case()` in the production runtime path;
2. `validate_recovery_action()` exists but does not have a complete production call path;
3. "requires human approval" is currently advisory metadata rather than a hard execution gate;
4. synchronous control-plane dispatch currently exists alongside the outbox;
5. webhook financial amounts require stronger independent reconciliation against authoritative merchant/order information;
6. some domain invariants are enforced by application code rather than database constraints;
7. recovery-case uniqueness is application-enforced rather than fully database-enforced;
8. financial-event append-only behavior is convention rather than a hard database immutability mechanism;
9. AI decision audit records do not currently persist every potentially useful proposal/evaluation field;
10. correlation IDs are not fully persisted through all audit records;
11. action/outbox terminal semantics have an identified consistency concern;
12. integration testing depends on a live PostgreSQL environment;
13. the original constitution's block table may differ from the implementation sequence used for Blocks 1–8;
14. frontend/demo and multi-agent stress-testing requirements may remain unimplemented depending on the authoritative constitution.

Codex must investigate these issues rather than assuming they are already resolved.

---

# 9. Repository Architecture

The project is structured as a **single deployable application**, not a microservice system.

Major directories:

```text
apps/
domain/
infrastructure/
alembic/
tests/
docs/
scripts/
```

## `apps/`

Application-facing code.

Primarily contains the FastAPI application, API routes, middleware, security, settings, and HTTP-specific behavior.

It should adapt HTTP requests to domain operations rather than embedding financial authority in route handlers.

---

## `domain/`

The core business/domain layer.

Contains framework-independent concepts such as:

* financial logic;
* recovery;
* policies;
* AI context/proposals;
* simulation;
* economics;
* observability.

The domain layer should remain as independent as practical from FastAPI, SQLAlchemy, and vendor SDKs.

---

## `infrastructure/`

Infrastructure adapters.

Includes:

* PostgreSQL/SQLAlchemy persistence;
* Razorpay parsing and security;
* LLM clients;
* structured logging;
* workers;
* execution adapters.

Infrastructure should implement external interfaces without becoming the authority for business rules that belong in the domain.

---

## `alembic/`

Database schema migrations.

Current migration sequence:

```text
001 → 002 → 003 → 004 → 005
```

---

## `tests/`

Contains unit and integration tests.

The default pytest configuration excludes integration tests unless explicitly requested.

---

## `docs/`

Contains architectural and operational documentation, including:

```text
PROJECT_CONSTITUTION.md
PRODUCTION_OPERATIONS.md
OBSERVABILITY_AND_EVALUATION.md
```

and simulation-related documentation where present.

---

## `scripts/`

Utility scripts such as AI/Gemini smoke or benchmark scripts.

---

# 10. Important Repository Components

Known important components include:

```text
apps/api/main.py
apps/api/settings.py

apps/api/routes/health.py
apps/api/routes/webhooks.py
apps/api/routes/ai_decisions.py
apps/api/routes/observability.py

apps/api/middleware/correlation.py
apps/api/middleware/error_handler.py

apps/api/security/auth.py

domain/shared/enums.py
domain/shared/errors.py

domain/recovery/state_machine.py
domain/recovery/execution.py
domain/recovery/control_plane.py
domain/recovery/orchestrator.py

domain/observability/metrics.py
domain/observability/service.py
domain/observability/simulation_evaluator.py

infrastructure/database/orm/recovery.py
infrastructure/database/orm/outbox.py
infrastructure/logging.py
infrastructure/workers/outbox_worker.py

alembic/versions/005_control_plane_outbox.py

tests/unit/test_control_plane.py
tests/unit/test_production_resilience.py
tests/integration/test_control_plane_e2e.py
tests/integration/test_operational_e2e.py
```

The exact current repository tree must always be inspected by Codex before modification. Do not invent files based solely on this document.

---

# 11. Project Constitution

The architectural authority document is:

```text
docs/PROJECT_CONSTITUTION.md
```

Codex must read this document before implementing architectural changes.

The constitution takes precedence over assumptions contained in previous completion reports.

Codex must:

1. read the constitution;
2. inspect the actual repository;
3. understand existing architecture;
4. preserve existing authority boundaries;
5. avoid casually changing architectural principles;
6. avoid introducing infrastructure not authorized by the architecture;
7. never assume a block is complete merely because an earlier report says "complete."

The constitution and repository together determine the real current state.

---

# 12. Financial Authority

Financial authority is deliberately distributed.

## AI

AI is **not authoritative** over:

* payment state;
* payment capture;
* money movement;
* merchant policy;
* database state;
* execution authorization;
* reconciliation.

## EconomicEngine

The `EconomicEngine` is authoritative for deterministic economic valuation.

It computes candidate economic values using the supplied model inputs.

## Webhook Reconciliation

Verified Razorpay webhook reconciliation is authoritative for payment-state transitions.

Recovery action execution must not directly mark a payment as `CAPTURED`.

The intended rule is:

```text
Recovery execution
≠
Payment capture
```

Only the authoritative payment reconciliation path may transition payment state to `CAPTURED`.

---

# 13. Payment State

Relevant payment states include states such as:

* `FAILED`
* `AUTHORIZED`
* `CAPTURED`

The exact complete enum set must be verified against the repository.

Important invariant:

```text
FAILED → AUTHORIZED/CAPTURED
```

may be valid under late-arriving authoritative events.

But once a payment is captured, recovery actions must not downgrade it.

The recovery control plane specifically checks for already-resolved payment states and can supersede stale recovery actions.

---

# 14. Monetary Integrity

All monetary values must use **integer minor units**.

For India:

```text
₹1 = 100 paise
```

Therefore:

```text
₹1000 = 100000 paise
```

Database financial amounts generally use:

```text
BIGINT
```

Monetary arithmetic must not use floating-point values.

Probabilities may use floats because probabilities are not financial balances.

This distinction is critical:

```text
money → integer minor units
probability → floating-point acceptable
```

Percentages/policy limits use integer representations where the domain defines them that way.

All rounding must be explicit and deterministic.

---

# 15. Observed Revenue vs Causal Incremental Revenue

A critical Block 6 correction must remain permanently understood.

The system uses:

```text
realized_captured_revenue_minor
```

for observed captured revenue.

This must **not** be described as:

```text
realized incremental revenue
```

unless a valid causal counterfactual experiment exists.

A captured payment proves that money was captured.

It does not prove that the recovery action caused the capture.

Therefore:

```text
observed captured revenue
≠
causal incremental revenue
```

Live production telemetry must remain observational unless an actual randomized control/holdout methodology exists.

Synthetic simulation may contain causal ground truth because the simulation explicitly defines counterfactual worlds.

---

# 16. AI Architecture

The AI system uses a structured proposal model.

Important concepts include:

```text
AIRecoveryContext
AIDecisionProposal
AIDecisionProvider
MockLLMClient
GeminiRESTClient
HttpOpenAIClient
```

The AI context is intentionally restricted.

`AIRecoveryContext` can contain observable information such as:

* payment information;
* behavioral aggregates;
* recovery history;
* merchant policy information;
* temporal context.

It must not contain hidden synthetic ground truth in production decision contexts.

---

# 17. AI Proposal

The AI produces structured data rather than arbitrary uncontrolled execution commands.

The proposal can contain fields such as:

* action;
* confidence;
* probability estimates;
* uncertainty;
* review indication;
* rationale;
* discount;
* related codes.

Pydantic/schema validation ensures malformed provider responses do not directly enter the decision system.

AI provider errors or malformed responses can trigger deterministic fallback behavior.

---

# 18. LLM Providers

Known provider architecture includes:

### `MockLLMClient`

Used for automated testing.

Tests must not consume live Gemini quota.

### `GeminiRESTClient`

Direct Gemini REST integration.

### `HttpOpenAIClient`

OpenAI-compatible/Ollama-style provider where implemented.

The provider abstraction prevents vendor-specific LLM logic from becoming embedded throughout the domain.

---

# 19. AI Authority Boundary

The central AI rule is:

> **The LLM proposes; deterministic systems decide and enforce.**

The LLM may influence:

* proposed recovery action;
* subjective probabilities;
* confidence;
* discount proposal;
* rationale;
* uncertainty.

The LLM must not directly:

* mutate payment status;
* capture payments;
* alter financial events;
* bypass merchant policy;
* override EconomicEngine calculations;
* execute recovery actions directly;
* change database authority;
* declare payment success.

Retries also must not call the LLM again.

---

# 20. Policy Engine

Merchant recovery policy constrains possible actions.

Policy rules include concepts such as:

* maximum completed interventions;
* cooldown period;
* discount bounds;
* high-value approval requirements.

The deterministic policy function:

```text
validate_action_against_policy
```

must remain authoritative over whether an AI proposal is permitted.

Known issue:

`validate_recovery_action()` exists and is tested but does not currently have a complete production call-site chain.

Another known concern is that:

> "requires human approval"

may currently be represented as advisory metadata rather than a hard control-plane gate.

This must not be silently treated as fully enforced.

Any future implementation addressing this must inspect the actual control-plane flow and determine the safest authoritative enforcement point.

---

# 21. EconomicEngine

The EconomicEngine is the deterministic economic authority.

It evaluates candidate recovery actions.

Important quantities include:

```text
expected_gross_recovery_minor
expected_natural_recovery_minor
expected_incremental_recovery_minor
intervention_cost_minor
ai_inference_cost_minor
expected_net_incremental_revenue_minor
```

The purpose is to compare intervention against the natural/no-intervention outcome.

The basic conceptual relationship is:

```text
Expected Incremental Recovery
=
Expected Gross Recovery
-
Expected Natural Recovery
```

and:

```text
Expected Net Incremental Revenue
=
Expected Incremental Recovery
-
Intervention Costs
-
AI Inference Costs
```

Exact implementation formulas must be read from the actual `EconomicEngine` rather than reconstructed from memory.

The LLM must not recreate these formulas independently.

---

# 22. Baseline and Oracle

Simulation/evaluation includes:

* deterministic baseline;
* AI strategy;
* oracle.

The oracle has access to synthetic ground truth and therefore must remain simulation-only.

The baseline represents a deterministic strategy against which AI can be compared.

The objective is not:

> "AI is better because it is AI."

The objective is to measure whether the AI strategy produces useful economic outcomes under controlled conditions.

---

# 23. Simulation Architecture

Synthetic simulations provide controlled scenarios.

They can model:

* natural recovery;
* action recovery;
* intervention effects;
* costs;
* payment outcomes;
* counterfactual worlds.

World A / World B concepts may be used to compare intervention versus non-intervention.

Synthetic ground truth must remain confined to simulation/evaluation components.

It must never be injected into:

```text
AIRecoveryContext
production observability
production payment reconciliation
production decision audit
```

in a way that creates hidden information leakage.

---

# 24. Evaluation Metrics

Known evaluation metrics include:

## Regret

Conceptually:

```text
Regret =
max(0, Oracle Net - AI Net)
```

in integer paise.

## Natural Recovery Probability MAE

```text
1/N × Σ |predicted natural probability - true natural probability|
```

## Action Recovery Probability MAE

```text
1/N × Σ |predicted action probability - true action probability|
```

## Brier Score

```text
1/N × Σ(predicted probability - actual binary outcome)^2
```

## Calibration

Five probability buckets are used:

```text
[0.0, 0.2)
[0.2, 0.4)
[0.4, 0.6)
[0.6, 0.8)
[0.8, 1.0]
```

An important Block 6 edge-case correction ensures negative AI net outcomes are not incorrectly classified as near-optimal merely because the oracle net is non-positive.

---

# 25. Razorpay Webhook Architecture

Webhook processing begins with the raw HTTP request.

The expected security sequence is:

```text
Raw request bytes
       ↓
HMAC-SHA256 verification
       ↓
constant-time signature comparison
       ↓
JSON parsing
       ↓
event validation
       ↓
event-ID deduplication
       ↓
durable PostgreSQL inbox
```

Signature verification must happen against the raw request body before relying on parsed JSON.

---

# 26. Webhook Replay Protection

Webhook requests contain an event ID.

The system persists webhook events in a durable inbox.

A PostgreSQL unique constraint protects against duplicate event IDs.

Duplicate delivery should produce an idempotent response such as:

```text
duplicate_ignored
```

without duplicating downstream financial side effects.

Concurrent duplicate ingestion must also be protected at the database level rather than relying solely on an application-level check.

---

# 27. Webhook Reconciliation

The webhook processor:

1. claims inbox events;
2. verifies/processes the event;
3. creates or locates relevant payment/order records;
4. reconciles payment state;
5. records payment attempt information;
6. creates append-only financial event records;
7. opens or resolves recovery cases as appropriate.

Only verified webhook processing should transition authoritative payment state.

---

# 28. Important Webhook Gap

The current implementation has a major known wiring gap:

```text
Webhook
→ case creation
```

exists, but:

```text
Webhook
→ RecoveryDecisionOrchestrator.orchestrate_case()
```

is not currently fully wired into the production runtime path.

Therefore a real accepted failed-payment webhook can create a recovery case without automatically triggering the AI decision/recovery-action flow.

This must be treated as a real architectural gap.

Do not describe the production system as fully end-to-end until this is resolved and verified.

---

# 29. Financial Amount Trust Gap

The constitution's intended principle is stronger than merely validating webhook signatures.

Webhook authenticity means:

> The event came from a trusted source.

It does not automatically prove that every financial field should be treated as an independently reconciled merchant truth.

The latest inspection identified that initial payment/order amounts are accepted from authenticated webhook data without a stronger independent merchant-order/Razorpay API reconciliation mechanism.

Future changes involving financial amount authority must explicitly investigate this.

Do not silently weaken the project's financial-integrity principle.

---

# 30. Database Architecture

PostgreSQL is the project's durable transactional source of truth.

The project intentionally does not depend on:

* Redis;
* Kafka;
* Celery;

for core persistence or transactional authority.

SQLAlchemy provides database access.

Alembic manages schema evolution.

Current migrations:

```text
001 → 002 → 003 → 004 → 005
```

---

# 31. Migration 001

Initial financial/recovery schema.

Known entities include:

* merchants;
* customers;
* orders;
* payments;
* payment attempts;
* merchant recovery policies;
* recovery cases;
* recovery actions;
* financial events.

---

# 32. Migration 002

Razorpay webhook/gateway schema.

Adds durable webhook inbox concepts and external Razorpay order/payment identifiers.

---

# 33. Migration 003

Simulation persistence.

Stores aggregate simulation-run information.

Synthetic ground truth itself remains conceptually an offline simulation concern and must not leak into production decision contexts.

---

# 34. Migration 004

AI decision persistence.

Stores AI decision records used for auditability and observability.

Known limitation: current persistence does not necessarily retain every useful detail of the raw proposal, policy evaluation, candidate economic evaluations, or correlation context.

---

# 35. Migration 005

Control Plane and transactional outbox schema.

Adds recovery-action fields including:

```text
idempotency_key
execution_attempt
max_retries
retry_count
next_retry_at
failure_reason
superseded_by_action_id
```

and creates:

```text
recovery_outbox_events
```

with:

* action ID;
* case ID;
* event type;
* status;
* JSON payload;
* idempotency key;
* attempt count;
* maximum attempts;
* next attempt time;
* creation time;
* processing time;
* error message.

Unique constraints protect action and outbox idempotency.

---

# 36. Important Database Invariants

Database integrity currently relies on a combination of:

* ORM definitions;
* PostgreSQL constraints;
* application validation;
* state-machine logic;
* transaction boundaries.

Known limitation:

Some domain constraints are not fully represented as PostgreSQL `CHECK` constraints or database-level enums.

Codex must not assume that because a Python validator exists, the database itself necessarily prevents an invalid state.

Similarly, recovery-case uniqueness currently relies more heavily on application logic than on a database partial unique constraint.

---

# 37. Recovery Actions

The recovery action catalogue is:

## `WAIT`

Do not actively intervene; allow observation/cooldown.

## `RETRY`

Perform a technical re-attempt.

## `PAYMENT_LINK`

Provide a payment-link-style recovery mechanism.

## `NOTIFY`

Send a customer notification.

## `ESCALATE`

Route the issue to a higher-touch support process.

Current executors are **test-mode simulations**.

They generate deterministic references such as:

```text
TEST_WAIT_*
TEST_RETRY_*
TEST_PLINK_*
TEST_NOTIF_*
TEST_TICKET_*
```

They do not move real money.

---

# 38. Recovery Action State Machine

The lifecycle is:

```text
PROPOSED
    ↓
APPROVED
    ↓
EXECUTING
    ↓
COMPLETED
FAILED
CANCELLED
EXPIRED
SUPERSEDED
```

Valid transitions include:

```text
PROPOSED
→ APPROVED
→ CANCELLED
→ EXPIRED
→ SUPERSEDED

APPROVED
→ EXECUTING
→ CANCELLED
→ EXPIRED
→ SUPERSEDED

EXECUTING
→ COMPLETED
→ FAILED
→ CANCELLED
→ EXPIRED
→ SUPERSEDED
```

Terminal states are:

```text
COMPLETED
FAILED
CANCELLED
EXPIRED
SUPERSEDED
```

Terminal states must not reactivate.

The state machine should reject invalid transitions deterministically.

---

# 39. Control Plane

Block 7 introduced the Recovery Action Control Plane.

Its purpose is to separate:

```text
decision generation
```

from:

```text
action lifecycle management
```

and:

```text
action execution
```

The Control Plane handles:

* lifecycle transitions;
* idempotency;
* stale-action protection;
* supersession;
* expiration;
* retry;
* execution dispatch;
* outbox interaction.

AI does not own the Control Plane.

---

# 40. Idempotency

Action idempotency keys are deterministically generated from:

```text
case_id
action_type
attempt_number
decision_id
```

using SHA-256.

Conceptually:

```text
SHA-256(
    recovery_action:
    case_id:
    action_type:
    attempt_number:
    decision_id
)
```

The actual implementation must remain authoritative.

PostgreSQL unique constraints enforce database-level uniqueness.

This is important because application-level duplicate checks are not sufficient under concurrent workers.

---

# 41. Concurrency

PostgreSQL row-level locking is used where required.

Important mechanisms include:

```text
FOR UPDATE
```

and:

```text
FOR UPDATE SKIP LOCKED
```

The latter allows multiple workers to claim separate outbox events without all workers competing for the same rows.

Concurrency behavior must always be tested rather than assumed.

---

# 42. Stale Action Protection

Before execution, the Control Plane checks conditions including:

1. action is not already terminal;
2. recovery case remains active;
3. payment has not already resolved;
4. action has not expired;
5. no newer action has superseded it.

If the payment is already:

```text
CAPTURED
```

or otherwise appropriately resolved, stale recovery work should not continue.

If the case is terminal, old recovery actions may become:

```text
SUPERSEDED
```

---

# 43. Action Expiration

The current implementation includes a 72-hour action TTL guard.

An action older than the configured lifetime can transition to:

```text
EXPIRED
```

rather than being executed indefinitely.

This protects against stale recovery decisions being executed long after their context is valid.

The exact TTL and configurability must be verified before future changes.

---

# 44. Supersession

If a newer active action exists for the same recovery case, an older action can become:

```text
SUPERSEDED
```

The action may retain a reference:

```text
superseded_by_action_id
```

This allows audit systems to understand why an action was not executed.

---

# 45. Retry Semantics

Execution failures are classified.

`ActionExecutionResult` contains structured information including concepts such as:

* success;
* execution reference;
* error code;
* error message;
* retryability.

Retryable failures may be retried up to a bounded maximum.

The current backoff concept is:

```text
delay_seconds = 2^retry_count × 10
```

Retries must remain deterministic and bounded.

---

# 46. AI Independence During Retry

Retries must **not**:

```text
call Gemini
```

and must not:

```text
re-evaluate the entire AI decision
```

A retry means:

> Re-dispatch the already approved deterministic action.

This prevents unstable AI output from changing an already approved execution decision merely because a worker encountered a temporary execution failure.

---

# 47. Transactional Outbox

The outbox exists to make dispatch intent durable.

The desired atomic operation is:

```text
BEGIN TRANSACTION

create/update recovery action
+
create outbox event

COMMIT
```

If the transaction rolls back:

```text
action absent
outbox event absent
```

There should not be an outbox event pointing to an action that never committed.

---

# 48. Outbox Lifecycle

Outbox states include concepts such as:

```text
PENDING
PROCESSING
COMPLETED
FAILED
SUPERSEDED
EXPIRED
```

Workers claim eligible events.

Processing uses:

```text
FOR UPDATE SKIP LOCKED
```

to allow concurrent workers.

Abandoned `PROCESSING` events can be reclaimed after a timeout.

The current implementation uses a 15-minute reclamation threshold.

---

# 49. Critical Outbox Architecture Question

The current system has both:

```text
transactional outbox
```

and:

```text
immediate synchronous Control Plane dispatch
```

This creates an architectural question.

Should:

```text
outbox
```

be the **exclusive authoritative dispatch mechanism**?

Or should synchronous dispatch remain as an intentional optimization?

Codex must inspect actual orchestration behavior and the constitution before deciding.

Do not blindly preserve both.

Do not blindly delete one.

The chosen design must avoid:

* double execution;
* inconsistent action/outbox state;
* lost events;
* misleading observability;
* bypassing durable dispatch guarantees.

---

# 50. Known Action/Outbox Consistency Risk

The latest repository inspection identified a possible inconsistency where an action may reach terminal `FAILED` semantics while its outbox event remains `PENDING`.

This is important because:

```text
terminal action
+
pending dispatch event
```

may create misleading system state.

Any future work in this area must define explicit invariants between:

```text
RecoveryActionStatus
```

and:

```text
OutboxEventStatus
```

and test them under:

* success;
* retry;
* non-retryable failure;
* maximum retry exhaustion;
* worker crash;
* duplicate dispatch.

---

# 51. Observability

Observability is strictly read-only.

It should never:

* mutate payments;
* execute recovery actions;
* change policies;
* approve actions;
* alter state.

Metrics include concepts such as:

```text
actions_proposed
actions_approved
actions_executing
actions_completed
actions_failed
actions_cancelled
actions_expired
actions_superseded
total_retries
pending_outbox_count
```

Block 8 added additional outbox processing/failure counts.

---

# 52. Observability APIs

Known endpoints include:

```text
GET /observability/summary
GET /observability/decisions/{decision_id}
GET /observability/recovery/{recovery_case_id}
POST /observability/simulation/evaluate
GET /observability/simulation/{id}
```

The exact current authorization and route semantics must be verified before modifying them.

The live observability layer must not expose hidden simulation ground truth.

---

# 53. Audit Trail

A complete conceptual audit should be capable of tracing:

```text
Payment / Recovery Case
        ↓
Observable Context
        ↓
AI Proposal
        ↓
Policy Result
        ↓
Economic Evaluation
        ↓
Approved Action
        ↓
Final Action
        ↓
Execution
        ↓
Outcome
```

The system deliberately distinguishes:

```text
AI proposed action
```

from:

```text
final authorized action
```

and:

```text
executed action
```

These must not be collapsed into a single field.

---

# 54. Audit Completeness Gaps

Current AI decision persistence may not contain all information desirable for a complete audit.

Known gaps include potentially missing persistence of:

* raw AI proposal;
* full rationale;
* complete policy result;
* complete candidate evaluations;
* correlation ID;
* complete execution linkage.

The audit service may reconstruct some information from related database records, but reconstruction is not equivalent to having persisted the original immutable decision context.

Future work must determine which fields are constitutionally required before modifying the schema.

---

# 55. Financial Events

Financial events are intended to form an append-only history.

They are used for important financial/reconciliation events.

Current append-only behavior is primarily an architectural/application convention.

There is no guarantee that every mutation is prevented by a database-level immutability mechanism.

If future work strengthens this, it must preserve historical records and avoid breaking reconciliation.

---

# 56. Block 8 API Hardening

Block 8 introduced production resilience concerns around:

* authentication;
* error handling;
* correlation;
* logging;
* health;
* readiness;
* worker lifecycle;
* configuration validation.

---

# 57. API Authentication

Administrative routes such as simulation and AI decision routes use configuration-driven API-key authentication.

The authentication mechanism uses constant-time comparison.

Important known behavior:

> Authentication is permissive when `ADMIN_API_KEY` is not configured.

This may be acceptable in development but must be carefully reviewed for production behavior.

Production configuration should not silently leave sensitive endpoints unauthenticated.

---

# 58. Error Handling

Structured errors use an envelope conceptually like:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Request validation failed.",
  "correlation_id": "...",
  "timestamp": "..."
}
```

Internal information must not leak through API responses.

Do not expose:

* stack traces;
* SQL statements;
* credentials;
* filesystem paths;
* internal secrets;
* LLM reasoning traces.

---

# 59. Correlation IDs

The middleware can obtain a correlation identifier from incoming request headers such as:

```text
X-Correlation-ID
X-Request-ID
```

or generate a UUID when absent.

Correlation IDs are placed into request context and response headers.

Block 8 audit work hardened the accepted correlation-ID format and length.

The exact persistence of correlation IDs into long-lived decision/audit records remains an identified gap.

---

# 60. Structured Logging

Structured logging includes information such as:

* timestamp;
* level;
* correlation ID;
* component metadata.

Sensitive values must be redacted.

Known secret categories include:

* API keys;
* passwords;
* bearer tokens;
* database connection strings;
* Google/Gemini API keys;
* payment identifiers where appropriate.

Logs must never become a secret exfiltration mechanism.

---

# 61. Health and Readiness

Two important concepts:

### `/health`

Liveness.

It answers:

> Is the process alive?

It should not require the database to be functioning merely to report process liveness.

### `/ready`

Readiness.

It checks whether the service can access required dependencies such as PostgreSQL.

A database failure should result in an appropriate non-ready response, such as:

```text
503
```

without leaking internal connection information.

---

# 62. Graceful Shutdown

FastAPI uses lifespan handling.

Shutdown should dispose of the asynchronous SQLAlchemy engine/connection pool.

The outbox worker supports a stop mechanism allowing active work to terminate cleanly where possible.

Worker shutdown must not knowingly corrupt transaction state.

---

# 63. Outbox Worker

Block 8 introduced a standalone outbox worker concept:

```text
python -m infrastructure.workers.outbox_worker
```

It can independently process recovery outbox events.

It handles:

* polling;
* transaction boundaries;
* dispatch;
* retry;
* abandoned event reclamation;
* graceful shutdown.

There is currently no equivalent continuously running webhook-worker daemon/CLI of exactly the same form.

The webhook batch processor is callable by external orchestration.

---

# 64. Security Threat Model

Important threats include:

## Forged webhook

Mitigated by HMAC-SHA256 verification and constant-time comparison.

## Replayed webhook

Mitigated by durable event IDs and PostgreSQL uniqueness.

## Concurrent duplicate webhook

Database uniqueness protects the race.

## Unauthorized administrative API

Mitigated by API-key authentication when configured.

## Secret leakage

Mitigated by settings sanitization and log redaction.

## Stack trace leakage

Mitigated by global exception handling.

## Header injection

Mitigated by correlation ID validation/length limits.

## Duplicate action execution

Mitigated by action state and idempotency controls.

## Stale recovery action

Mitigated by case/payment/expiration/supersession guards.

## Worker crash

Mitigated by outbox persistence and abandoned `PROCESSING` reclamation.

---

# 65. Testing Architecture

The test architecture is a major part of the project.

Tests cover:

* state machines;
* financial arithmetic;
* policies;
* webhook security;
* reconciliation;
* AI schemas;
* provider fallback;
* simulation;
* economic evaluation;
* observability;
* recovery control plane;
* resilience;
* health;
* authentication;
* errors.

---

# 66. Mock LLM Requirement

Automated tests must use:

```text
MockLLMClient
```

and must consume:

```text
0 live Gemini tokens
```

The test configuration includes an autouse fixture that forces mock AI behavior.

Future Codex work must preserve this.

A test suite must never accidentally begin consuming production Gemini quota simply because an environment variable is present.

---

# 67. Integration Tests

Integration tests require a real PostgreSQL environment.

Important distinction:

```text
Unit tests passing
```

does not mean:

```text
PostgreSQL integration tests passing
```

Likewise:

```text
Integration tests implemented
```

does not mean:

```text
Integration tests executed against live PostgreSQL
```

Codex must report these separately.

Previous verification showed situations where PostgreSQL/Docker was unavailable.

Therefore claims such as:

> "all integration tests passed"

must only be made when actual execution evidence exists.

---

# 68. Current Test History

Block 6 reported:

```text
240 total tests
218 unit
22 PostgreSQL integration
```

Block 7 later reported:

```text
233 unit tests passing
```

Block 8 reported:

```text
256 unit tests passing
```

The latest available test evidence after Block 8 includes:

```text
256 passed
```

for the unit suite.

However, the exact current test count must always be verified by running pytest rather than relying on historical numbers.

---

# 69. Block History

## Block 1 — Financial/Recovery Foundation

Established foundational domain models, policies, financial concepts, recovery cases/actions, state machines, and initial database schema.

The objective was to establish the deterministic financial/recovery foundation before introducing AI.

---

## Block 2 — Razorpay Webhook Gateway

Introduced:

* webhook parsing;
* raw-body signature verification;
* HMAC;
* event IDs;
* durable inbox;
* replay protection;
* payment reconciliation;
* payment attempts;
* financial events.

The objective was to establish authoritative payment-event ingestion.

---

## Block 3 — Simulation and Economic Model

Introduced:

* synthetic scenarios;
* counterfactual simulation;
* baseline;
* oracle;
* EconomicEngine;
* simulation persistence;
* economic evaluation.

The objective was to establish a way to evaluate recovery strategies economically before relying on AI.

---

## Block 4 — AI Decision Layer

Introduced:

* AI context;
* structured proposal schema;
* provider abstraction;
* Gemini provider;
* mock provider;
* OpenAI-compatible provider;
* validation;
* fallback;
* AI decision persistence.

The objective was to introduce AI as a bounded proposal mechanism.

---

## Block 5 — Recovery Orchestration and Execution

Introduced the recovery decision orchestration path and test-mode recovery executors.

The objective was to connect:

```text
context
→ AI
→ policy
→ economic evaluation
→ recovery decision
→ action
```

without giving AI direct financial authority.

---

## Block 6 — Decision Observability and Evaluation

Introduced:

* decision observability;
* economic metrics;
* audit reconstruction;
* live vs simulation distinction;
* regret;
* calibration;
* Brier score;
* MAE;
* comparative evaluation.

Important audit correction:

```text
realized_captured_revenue_minor
```

replaced terminology that incorrectly implied causal incremental revenue.

A zero-oracle near-optimality edge case was also corrected.

---

## Block 7 — Recovery Action Control Plane

Introduced:

* deterministic action lifecycle;
* action execution contracts;
* idempotency;
* PostgreSQL unique constraints;
* transactional outbox;
* retries;
* stale-action protection;
* supersession;
* expiration;
* outbox processing;
* control-plane observability.

Later audit work added:

* 72-hour expiration guard;
* abandoned outbox-event reclamation;
* context construction hardening.

---

## Block 8 — Production Resilience

Introduced:

* API authentication;
* structured error responses;
* correlation IDs;
* secret-safe logging;
* health/readiness;
* graceful shutdown;
* standalone outbox worker;
* production configuration safeguards.

Later audit work hardened:

* correlation-ID sanitization;
* database URL/API-key log masking;
* `/health` contract compatibility;
* worker lifecycle behavior.

---

# 70. Implementation → Audit Workflow

This project follows a strict workflow.

```text
IMPLEMENTATION
      ↓
IMPLEMENTATION COMPLETION REPORT
      ↓
INDEPENDENT ARCHITECTURAL AUDIT
      ↓
AUDIT FIXES
      ↓
FINAL VERIFICATION
      ↓
BLOCK LOCKED
```

This distinction is mandatory.

## Implementation Phase

The developer/Codex implements the requested block.

It should:

* inspect;
* plan;
* modify;
* test;
* document;
* report;
* stop.

## Audit Phase

Only afterward should an independent audit be performed.

The audit should challenge the implementation rather than simply agreeing with the completion report.

It should inspect:

* architecture;
* code;
* state transitions;
* database;
* transactions;
* security;
* financial boundaries;
* concurrency;
* edge cases;
* tests;
* documentation.

**Do not combine implementation and audit unless explicitly instructed.**

---

# 71. Current Known Risks

The following issues are known and should remain visible to future Codex sessions.

## Risk 1 — Webhook → Orchestrator Wiring

Recovery cases can be created from webhook processing without the production runtime automatically invoking:

```text
orchestrate_case()
```

This is probably one of the most important future integration gaps.

---

## Risk 2 — Policy Validation Call Sites

`validate_recovery_action()` exists but its complete production enforcement path must be verified.

---

## Risk 3 — Human Approval

A high-value action may indicate:

```text
requires approval
```

without necessarily being blocked at the Control Plane.

This needs explicit semantics.

---

## Risk 4 — Synchronous Dispatch vs Outbox

The system currently has both mechanisms.

Future architecture must determine whether the outbox should become the exclusive dispatch authority.

---

## Risk 5 — Webhook Financial Amount Trust

Authenticated webhook payloads are not necessarily equivalent to independently reconciled merchant financial truth.

The amount-authority principle needs stronger verification.

---

## Risk 6 — Database Constraints

Some state/domain invariants exist only in application code.

Where appropriate, important financial/state invariants should be considered for database-level enforcement.

---

## Risk 7 — Recovery Case Uniqueness

Application-level uniqueness may be insufficient under concurrent requests.

Database-level partial uniqueness may be appropriate depending on the business invariant.

---

## Risk 8 — Financial Event Immutability

Append-only behavior is not necessarily database-enforced.

Future changes must preserve financial history.

---

## Risk 9 — AI Audit Completeness

The current AI decision record may not contain:

* raw proposal;
* complete rationale;
* full policy result;
* candidate evaluations;
* correlation ID.

Determine what is required before expanding the schema.

---

## Risk 10 — Correlation Persistence

Request correlation can exist at runtime without being persisted into every audit record.

If audit traceability requires it, this should be explicitly designed.

---

## Risk 11 — Action/Outbox Terminal Consistency

Action and outbox states may become semantically inconsistent under failure.

Future implementation must establish explicit state invariants.

---

## Risk 12 — Integration Environment

PostgreSQL integration tests cannot be claimed as executed unless PostgreSQL is actually available.

---

## Risk 13 — Constitution Block Mismatch

Previous implementation blocks may not exactly correspond to the block numbering/table in the constitution.

Codex must use the constitution as the authoritative source when determining future scope.

If the constitution says a capability belongs to a different block, do not silently rewrite history.

---

## Risk 14 — Frontend / Demo

The current repository inspection indicates no frontend implementation.

If the constitution requires a frontend/demo stage, this remains future work.

Do not assume the backend being complete means the entire hackathon product is complete.

---

## Risk 15 — Multi-Agent Stress Testing

The original constitutional roadmap may include multi-agent stress testing.

No such complete implementation should be assumed merely because the system supports multiple workers.

Worker concurrency is not equivalent to multi-agent evaluation.

---

# 72. Technology Stack

Known technologies include:

* Python;
* FastAPI;
* Pydantic;
* SQLAlchemy;
* PostgreSQL;
* Alembic;
* pytest;
* asynchronous Python;
* Gemini REST integration;
* OpenAI-compatible HTTP LLM integration;
* MockLLMClient;
* Docker configuration where present.

Codex must inspect:

```text
pyproject.toml
```

before adding or changing dependencies.

Do not invent dependencies.

Do not introduce Redis/Kafka/Celery/microservices unless explicitly authorized by a new requirement and reconciled with the constitution.

---

# 73. Codex Operating Rules

These rules are mandatory for future development.

## Rule 1 — Inspect Before Modifying

Never modify the repository based only on this document.

First inspect the actual repository.

---

## Rule 2 — Constitution First

Before architectural changes:

```text
docs/PROJECT_CONSTITUTION.md
```

must be read.

---

## Rule 3 — Repository Is More Authoritative Than Reports

Previous completion/audit reports are historical context.

Actual code, schema, tests, and configuration determine current implementation.

---

## Rule 4 — Preserve Authority Boundaries

AI must never become authoritative over:

* money;
* payment state;
* reconciliation;
* merchant policy;
* execution;
* financial-event creation authority.

---

## Rule 5 — No Silent Architecture Changes

Do not introduce:

* Redis;
* Kafka;
* Celery;
* microservices;
* alternative databases;

merely because they appear convenient.

---

## Rule 6 — Financial Correctness First

Money must remain integer minor units.

Never introduce floating-point monetary storage.

---

## Rule 7 — No Fake Completeness

Do not call something:

```text
production ready
```

simply because:

```text
pytest passed
```

Tests are evidence, not proof of complete architecture.

---

## Rule 8 — Test Actual Boundaries

Tests should verify:

* real state transitions;
* transaction behavior;
* concurrency;
* idempotency;
* financial safety;
* policy enforcement;
* failure handling.

Do not create tests merely to inflate counts.

---

## Rule 9 — Minimal Changes

Do not rewrite stable architecture unnecessarily.

Prefer targeted changes that preserve existing behavior.

---

## Rule 10 — Explain Tradeoffs

If multiple architectural solutions exist:

1. inspect the repository;
2. compare against the constitution;
3. identify safety implications;
4. choose the least risky compatible approach.

---

## Rule 11 — Never Invent Infrastructure

If a dependency, database, credential, service, or environment is unavailable, say so.

Do not fabricate successful execution.

---

## Rule 12 — Separate Implementation and Audit

Do not perform an independent architectural audit during implementation unless explicitly instructed.

The normal workflow is:

```text
implementation
→ completion report
→ separate audit prompt
```

---

## Rule 13 — Do Not Trust Previous "PASS" Labels

A previous audit saying:

```text
PASSED
```

does not mean every hidden runtime path is correct.

Always inspect the actual current repository.

---

## Rule 14 — Do Not Hide Known Gaps

If implementation discovers a discrepancy, report it.

Do not silently work around it and claim the architecture is complete.

---

## Rule 15 — Preserve Test Isolation

Normal automated tests must use:

```text
MockLLMClient
```

and consume:

```text
0 live Gemini quota
```

---

## Rule 16 — Never Give AI Synthetic Ground Truth

Production AI context must never contain simulation-only truth.

---

## Rule 17 — Recovery Execution Is Not Payment Capture

No recovery executor should directly mark a payment as captured.

---

## Rule 18 — Observability Is Read-Only

Observability must not modify business state.

---

# 74. Future Block Development Protocol

Every future block should follow this sequence.

## Phase A — Implementation

Codex should:

1. read this project context;
2. read `PROJECT_CONSTITUTION.md`;
3. inspect the actual repository;
4. inspect relevant existing code;
5. understand previous blocks;
6. identify dependencies and risks;
7. implement only the requested block;
8. add/update appropriate tests;
9. run appropriate tests;
10. distinguish unit vs integration verification;
11. report exact changes;
12. report anything not verified;
13. stop.

The implementation prompt should not automatically ask Codex to perform an independent audit.

---

# 75. Phase B — Independent Audit

After implementation has finished, an independent audit prompt may be given.

The audit should:

* inspect actual implementation;
* challenge the implementation report;
* compare against the constitution;
* compare against project context;
* identify security issues;
* identify financial safety issues;
* inspect authority boundaries;
* inspect concurrency;
* inspect database behavior;
* inspect state machines;
* inspect transactions;
* inspect error paths;
* inspect edge cases;
* inspect tests;
* inspect documentation;
* identify false claims;
* apply fixes only when the audit request explicitly authorizes fixes;
* rerun appropriate tests;
* produce a final verdict.

The audit should be skeptical.

A passing test count is not enough.

---

# 76. Documentation Rules

Documentation is part of the engineering system.

The following must remain consistent with the repository:

```text
PROJECT_CONSTITUTION.md
PROJECT_CONTEXT.md
OBSERVABILITY_AND_EVALUATION.md
PRODUCTION_OPERATIONS.md
```

Documentation must never claim functionality that the code does not actually implement.

When a capability is partial, documentation should say:

```text
PARTIALLY IMPLEMENTED
```

or:

```text
IMPLEMENTED BUT NOT FULLY WIRED
```

rather than pretending it is complete.

---

# 77. What Codex Should Do at the Start of Every New Block

Before writing code, Codex should answer internally:

```text
1. What does the constitution require?
2. What does the current repository actually contain?
3. Which previous block owns this responsibility?
4. Which component is authoritative?
5. What new capability is this block adding?
6. What existing invariants could this change break?
7. What database changes are required?
8. What concurrency issues exist?
9. What financial safety issues exist?
10. What tests prove the new behavior?
11. What remains unverifiable in the current environment?
```

Only then should implementation begin.

---

# 78. Architectural Mental Model

The project should ultimately be understood as:

```text
Razorpay
    ↓
provides payment events

PostgreSQL
    ↓
provides durable transactional truth

Webhook reconciliation
    ↓
owns authoritative payment-state transitions

Recovery cases
    ↓
represent recoverable payment failures

AI
    ↓
proposes possible recovery strategies

Merchant policy
    ↓
deterministically constrains proposals

EconomicEngine
    ↓
calculates financial value

Orchestrator
    ↓
coordinates decision creation

Control Plane
    ↓
governs action lifecycle

Transactional Outbox
    ↓
provides durable dispatch intent

Executors
    ↓
currently simulate recovery execution

Observability
    ↓
explains what happened

Simulation
    ↓
evaluates whether the strategy works
```

The most important conceptual rule is:

> **AI is inside the system, not above the system.**

AI should never become the authority simply because it is the most sophisticated component.

---

# 79. Final Architectural Principle

Financial Agent Lab is ultimately trying to demonstrate a specific engineering philosophy:

> **Use AI where uncertainty and contextual reasoning are useful, but surround AI with deterministic financial, policy, execution, persistence, and reconciliation controls.**

The architecture therefore intentionally separates:

```text
AI reasoning
```

from:

```text
financial truth
```

and:

```text
execution authority
```

and:

```text
payment reconciliation
```

and:

```text
merchant policy
```

and:

```text
observability
```

The desired system is not one where an LLM says:

> "Capture the payment."

Instead, it is one where:

```text
Razorpay event
    ↓
verified payment fact
    ↓
recovery case
    ↓
observable context
    ↓
AI proposal
    ↓
deterministic policy
    ↓
deterministic economic evaluation
    ↓
controlled action lifecycle
    ↓
durable dispatch
    ↓
safe execution
    ↓
authoritative reconciliation
    ↓
auditable result
```

That separation is the foundation of the entire project.

---

# 80. Codex Instruction — Final

**Treat this document as persistent architectural context, not as a replacement for inspecting the repository.**

For every future task:

```text
READ CONTEXT
     ↓
READ CONSTITUTION
     ↓
INSPECT REPOSITORY
     ↓
UNDERSTAND CURRENT STATE
     ↓
IMPLEMENT REQUESTED SCOPE ONLY
     ↓
TEST
     ↓
REPORT
     ↓
STOP
```

Then, only when explicitly requested:

```text
INDEPENDENT AUDIT
     ↓
CHALLENGE
     ↓
VERIFY
     ↓
FIX IF AUTHORIZED
     ↓
RETEST
     ↓
FINAL VERDICT
```

The project is currently **implemented through Block 8**, but the repository contains known architectural gaps and partially wired paths. Future development must build from the **actual current repository state**, not from optimistic historical completion claims.

**Never trade financial correctness for convenience.**

**Never trade deterministic authority for AI autonomy.**

**Never claim verification that was not actually performed.**

**Never allow an AI proposal to become financial truth.**

**Never allow recovery execution to become payment reconciliation.**

**Never allow documentation to become more complete than the code.**

And above all:

> **Financial Agent Lab is a financially safe, deterministic recovery decision system with AI as a bounded proposal component — not an AI system that directly controls payments.**

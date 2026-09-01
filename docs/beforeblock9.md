

---

# BLOCK 9 — AUTHORITATIVE RECOVERY DECISION PIPELINE

## IMPLEMENTATION-ONLY SPECIFICATION

### IMPORTANT WORKFLOW RULE

This is an **IMPLEMENTATION TASK ONLY**.

Do **not** perform the independent architectural audit during this task.

The required workflow is:

```text
READ CONTEXT
    ↓
INSPECT REPOSITORY
    ↓
IMPLEMENT BLOCK 9
    ↓
RUN TESTS / VERIFY
    ↓
WRITE IMPLEMENTATION COMPLETION REPORT
    ↓
STOP
```

A separate independent architectural audit will be performed **after this implementation is complete**.

Do not mix audit and implementation phases.

---

# 1. PROJECT CONTEXT

You are working on:

**Financial Agent Lab**

Repository:

```text
C:\financial-agent-lab
```

This is a Python/FastAPI/PostgreSQL financial recovery decision prototype developed for a Razorpay AI Buildathon.

Before modifying anything, you MUST read:

```text
docs/PROJECT_CONSTITUTION.md
docs/PROJECT_CONTEXT.md
```

You MUST also inspect the actual repository and current implementation.

These documents are architectural context, not substitutes for inspecting the code.

### Authority hierarchy

When determining what is actually implemented:

```text
ACTUAL REPOSITORY CODE
        >
PROJECT_CONSTITUTION.md
        >
PROJECT_CONTEXT.md
        >
PREVIOUS COMPLETION REPORTS
```

Previous completion/audit reports are historical information only.

Do not assume something exists merely because an earlier report claimed that it was implemented.

---

# 2. CURRENT ARCHITECTURAL STATE

Blocks 1–8 have already been implemented.

The current system contains:

* FastAPI API layer
* PostgreSQL persistence
* SQLAlchemy async ORM
* Alembic migrations 001–005
* Razorpay webhook verification/inbox/reconciliation
* Recovery cases
* Recovery actions
* deterministic policy validation
* EconomicEngine
* AI proposal layer
* Gemini provider
* MockLLMClient
* simulation/evaluation
* observability
* recovery action state machine
* recovery control plane
* transactional recovery-action outbox
* outbox worker
* API authentication
* error sanitization
* correlation IDs
* structured logging
* health/readiness endpoints
* extensive unit tests
* PostgreSQL integration tests

However, repository inspection after Block 8 confirmed that the system is **not yet a completely authoritative end-to-end recovery pipeline**.

The largest current gap is:

```text
verified webhook
    ↓
reconciliation
    ↓
recovery case
    ↓
[NO DURABLE RUNTIME HANDOFF]
    ↓
RecoveryDecisionOrchestrator
```

`RecoveryDecisionOrchestrator.orchestrate_case()` exists but is not connected to the real production webhook/recovery runtime path.

This Block 9 exists primarily to close that architectural break.

---

# 3. BLOCK 9 OBJECTIVE

Build the:

# **Authoritative Recovery Decision Pipeline**

The system must become a coherent durable pipeline in which a verified failed payment can progress through:

```text
Razorpay webhook
    ↓
Webhook authentication
    ↓
Durable webhook inbox
    ↓
Authoritative payment reconciliation
    ↓
Recovery case
    ↓
Durable decision request
    ↓
Decision worker
    ↓
RecoveryDecisionOrchestrator
    ↓
AI proposal
    ↓
Deterministic policy validation
    ↓
Deterministic authorization
    ↓
Economic evaluation
    ↓
Deterministic final action selection
    ↓
Recovery Action
    ↓
APPROVED / PENDING_APPROVAL
    ↓
Transactional action outbox
    ↓
Exclusive Outbox Worker
    ↓
Control Plane
    ↓
Test-mode executor
    ↓
Execution result
    ↓
Audit / observability
    ↓
Later Razorpay webhook reconciliation
```

The system must remain financially safe.

---

# 4. NON-NEGOTIABLE ARCHITECTURAL RULES

These rules MUST NOT be violated.

## Rule 1 — AI is not authoritative

The LLM may propose:

* action
* confidence
* probabilities
* discount
* rationale
* uncertainty
* review indication

The LLM may NOT directly:

* mutate payment state
* mark payment captured
* determine authoritative payment amount
* bypass merchant policy
* approve its own action
* execute financial operations
* create authoritative financial events
* bypass the control plane

---

# 5. PAYMENT STATE AUTHORITY

Only verified Razorpay webhook reconciliation may transition payment state.

Recovery execution MUST NOT:

```text
payment.status = CAPTURED
```

or otherwise directly manipulate payment reconciliation state.

The only valid path for payment capture remains:

```text
verified Razorpay event
    ↓
webhook reconciliation
    ↓
payment state transition
```

A recovery executor merely performs a recovery intervention.

Execution is NOT payment capture.

---

# 6. MONETARY INTEGRITY

All monetary values must remain:

```text
integer minor units
BIGINT
paise
```

Never introduce floating-point monetary storage.

Probabilities may use floats.

Money may not.

Preserve the distinction between:

```text
expected economic values
```

and:

```text
observed captured revenue
```

The live observability field:

```text
realized_captured_revenue_minor
```

must NEVER be renamed or described as causal incremental revenue.

Do not introduce unsupported causal claims.

---

# 7. POSTGRESQL AUTHORITY

PostgreSQL remains the durable source of truth.

Do not introduce:

* Redis
* Kafka
* Celery
* RabbitMQ
* another database
* microservices
* distributed brokers

unless explicitly authorized.

This project remains a single deployable application with worker processes around PostgreSQL.

---

# 8. FIRST TASK — INSPECT BEFORE MODIFYING

Before writing code:

1. Read `docs/PROJECT_CONSTITUTION.md`.
2. Read `docs/PROJECT_CONTEXT.md`.
3. Inspect the current repository tree.
4. Inspect:

   * webhook route
   * webhook processor
   * recovery case creation
   * `RecoveryDecisionOrchestrator`
   * AI provider
   * policy validator
   * action validator
   * EconomicEngine
   * control plane
   * outbox ORM
   * recovery ORM
   * AI decision ORM
   * financial event ORM
   * current migrations
   * current workers
   * current tests
5. Trace actual runtime call paths.
6. Do not rely solely on documentation.

Before changing architecture, explicitly determine the existing transaction boundaries.

---

# 9. DURABLE FAILED-CASE → DECISION HANDOFF

The first major requirement is to create a durable handoff from a newly actionable recovery case to the decision orchestration layer.

## Required behavior

When a failed payment creates a recovery case that is eligible for recovery decisioning:

```text
RecoveryCase
    ↓
durable decision request
```

The webhook request itself MUST NOT:

* call Gemini
* call an LLM
* execute recovery actions
* perform synchronous AI orchestration

The webhook processing path must remain responsible for:

* authentication
* inbox persistence
* reconciliation
* case state
* durable event/request creation

Decisioning must happen asynchronously after the reconciliation transaction has committed.

---

# 10. DECISION REQUEST DESIGN

Introduce a durable decision-request mechanism.

You may choose between:

### Option A — Dedicated decision request table

A case-owned table representing:

```text
recovery decision requested
```

with fields such as:

* id
* recovery_case_id
* payment_id if appropriate
* request status
* attempt count
* max attempts
* next attempt timestamp
* created timestamp
* processed timestamp
* error information
* correlation ID if appropriate
* deterministic idempotency key
* case/version information if required

### Option B — Generic domain outbox

A generalized durable event mechanism capable of representing:

```text
recovery.decision_requested
```

Do NOT choose blindly.

Inspect the existing architecture first.

For this prototype, prefer the simpler explicit design unless repository evidence strongly supports a generic domain-event architecture.

The decision request must be:

* durable
* idempotent
* concurrency safe
* retryable
* observable

---

# 11. DECISION REQUEST IDEMPOTENCY

There must not be multiple active decision requests causing duplicate decision work for the same recovery state.

Use PostgreSQL-backed uniqueness where appropriate.

Consider:

```text
case_id + case state/version
```

or another deterministic representation.

Do not merely perform:

```python
if not exists:
    insert
```

without database-level protection against races.

Concurrent workers must not create duplicate active requests.

---

# 12. TRANSACTION BOUNDARIES

Maintain clear transaction boundaries.

### Transaction A — Webhook ingestion

```text
verify webhook
→ deduplicate event
→ persist inbox
```

### Transaction B — Reconciliation

```text
claim inbox event
→ reconcile payment
→ update order/payment
→ create/update payment attempt
→ append financial event
→ open/recover case
→ create durable decision request if required
→ commit
```

No LLM call inside this transaction.

### Transaction C — Decision worker

```text
claim decision request
→ lock/validate case
→ construct context
→ run orchestrator
→ persist decision/action
→ persist action outbox if executable
→ commit
```

Do not hold database locks while making slow external LLM calls unless there is a compelling reason and the locking strategy explicitly prevents deadlocks/timeouts.

If necessary, design the worker state transitions so a request is safely claimed before external work.

### Transaction D — Action outbox

```text
claim outbox event
→ validate action
→ execute
→ persist execution result/state
→ commit
```

---

# 13. WEBHOOK → DECISION HANDOFF MUST BE ASYNCHRONOUS

The production webhook route must never become:

```text
Webhook
→ Gemini
→ policy
→ economics
→ execution
→ response
```

It must remain:

```text
Webhook
→ authenticate
→ durable inbox
→ later reconciliation
→ durable decision request
→ return/continue
```

Decisioning belongs to worker execution.

---

# 14. UNKNOWN WEBHOOK AMOUNT PROTECTION

This is a critical financial correction.

Current repository behavior can create internal payment/order financial records from webhook-provided amount when no authoritative internal record exists.

That conflicts with the project's financial-source-of-truth requirement.

Do NOT silently preserve this behavior.

The Block 9 implementation must establish a safe rule.

### Required principle

An authenticated webhook payload is evidence of an external event.

It is NOT automatically the authoritative merchant financial amount.

For a recovery-eligible payment:

```text
authoritative internal order/payment amount
        ↓
must already exist
```

If no authoritative internal financial record exists:

```text
webhook
→ durable inbox
→ unmatched/quarantined reconciliation state
→ NO recovery case
→ NO economic decision
→ NO recovery action
```

Do not use an untrusted webhook amount to calculate recovery economics.

---

# 15. IMPORTANT: DO NOT INVENT A NEW AMOUNT SOURCE

The current repository does not have a fully implemented independent merchant order registry/Razorpay API lookup authority.

Do NOT casually introduce one.

If the repository lacks an approved authoritative source for an unmatched webhook:

* preserve the webhook event
* mark it appropriately as unmatched/quarantined
* make the condition observable
* do not create a recovery case based on the webhook amount alone

A future block can explicitly design an authoritative amount source.

---

# 16. POLICY MUST BE A REAL GATE

The current repository contains policy validation, but policy enforcement is not strong enough at the final execution boundary.

Block 9 must establish a deterministic policy gate.

The sequence must be:

```text
AI proposal
    ↓
proposal validation
    ↓
policy eligibility
    ↓
authorization
    ↓
economic evaluation
    ↓
final action selection
    ↓
control-plane validation
    ↓
execution
```

Policy must not be advisory metadata.

---

# 17. POLICY RESPONSIBILITIES

Policy validation must deterministically enforce applicable rules including:

* maximum intervention count
* cooldown
* allowed actions
* discount limits
* merchant configuration
* high-value approval requirements
* any existing policy constraints already defined in the repository

Do not duplicate policy formulas unnecessarily.

Reuse the authoritative existing policy validator.

---

# 18. AUTHORIZATION MUST BE DISTINCT FROM POLICY

Policy answers:

> "Is this action allowed by merchant policy?"

Authorization answers:

> "Is this action authorized to execute right now?"

These must not be conflated.

For example:

```text
Policy:
PAYMENT_LINK is allowed
```

does not necessarily mean:

```text
Payment Link may execute immediately.
```

if the action requires human approval.

---

# 19. HIGH-VALUE HUMAN APPROVAL

The existing:

```text
requires_approval
```

behavior is currently advisory.

Block 9 must turn this into an actual execution boundary.

Preferred design:

```text
PROPOSED
    ↓
PENDING_APPROVAL
    ↓
APPROVED
    ↓
EXECUTING
    ↓
COMPLETED / FAILED / ...
```

If the existing state model makes a different safe design more appropriate, inspect it carefully before modifying it.

However, the invariant is mandatory:

> A high-value action requiring approval MUST NOT execute before explicit approval.

---

# 20. APPROVAL RECORD

Approval must be attributable and auditable.

An approval operation should capture, as appropriate:

* action ID
* case ID
* actor identity
* decision
* timestamp
* reason/comment if supported
* correlation ID
* schema/version information

Do not implement anonymous implicit approval.

Do not allow the AI to approve its own action.

Do not treat:

```text
requires_approval=True
```

as sufficient authorization.

---

# 21. APPROVAL API

If an API operation is required for approval:

* protect it with the existing administrative authentication boundary
* use constant-time API-key verification where that mechanism remains the configured mechanism
* do not make approval publicly accessible
* do not introduce a new authentication system unnecessarily

The approval endpoint must not directly mutate payment capture state.

It may only authorize a recovery action.

---

# 22. FINAL ACTION SELECTION

This is another critical authority issue.

Currently the AI provider can return the raw AI-selected action even when deterministic policy/economic processing has identified another permitted action.

Do not allow this to remain ambiguous.

The safer architecture is:

```text
AI proposal = recorded proposal
```

while:

```text
final executable action
```

is determined by deterministic policy + authorization + EconomicEngine results.

The LLM's proposal must never bypass deterministic eligibility.

If the AI proposes an invalid action:

```text
AI proposal
→ policy rejection
→ deterministic fallback
```

If multiple actions are permitted:

```text
EconomicEngine
→ deterministic candidate evaluation
→ deterministic selection
```

The implementation must clearly define which component determines the final action.

Do not invent an undocumented ranking rule.

Use the existing EconomicEngine semantics where possible.

---

# 23. PRESERVE AI ATTRIBUTION

Do not overwrite the original AI proposal with the final deterministic selection.

Persist separately:

```text
ai_proposed_action
```

and:

```text
deterministic_selected_action
```

and, if applicable:

```text
final_approved_action
```

This distinction is essential for auditability.

---

# 24. ECONOMIC ENGINE AUTHORITY

The EconomicEngine remains authoritative for:

* expected gross recovery
* expected natural recovery
* expected incremental recovery
* intervention cost
* AI inference cost where applicable
* expected net incremental revenue
* policy-permitted candidate evaluation
* candidate ranking/selection according to existing engine semantics

Do not recreate economic formulas inside:

* AI provider
* API routes
* control plane
* worker
* executor

Reuse the existing engine.

---

# 25. OUTBOX MUST BECOME THE EXCLUSIVE ACTION DISPATCH PATH

This is an explicit Block 9 requirement.

Currently:

```text
orchestrator
→ create action + outbox
→ immediate synchronous dispatch
```

This creates two possible dispatch paths.

Remove the ambiguity.

The desired architecture is:

```text
Orchestrator
    ↓
persist approved action
    +
persist action outbox event
    ↓
COMMIT
    ↓
Outbox Worker
    ↓
Control Plane
    ↓
Executor
```

The orchestrator must NOT synchronously execute the action after persisting it.

---

# 26. IMPORTANT OUTBOX SEMANTICS

The outbox provides:

> durable intent to dispatch

It does not provide exactly-once delivery.

The architecture should be described as:

```text
at-least-once delivery
+
idempotent execution
```

Do not claim exactly-once distributed execution.

---

# 27. OUTBOX WORKER AUTHORITY

Only the outbox worker should initiate recovery action execution.

The following must NOT execute recovery actions:

* webhook route
* webhook reconciliation
* AI provider
* decision API
* orchestrator
* observability service
* frontend

They may create durable intent where appropriate.

Only the outbox worker dispatches.

---

# 28. CONTROL PLANE REVALIDATION

Even if earlier layers validated policy and authorization, the control plane must perform final safety validation before execution.

At minimum verify:

* action status
* action not terminal
* action not expired
* action not superseded
* case still active
* payment not already resolved
* action is authorized
* policy constraints remain valid
* idempotency key
* execution attempt/retry state

The control plane is the last deterministic execution boundary.

---

# 29. LATE PAYMENT CAPTURE

If a payment becomes:

```text
CAPTURED
```

before a queued recovery action executes:

```text
action → SUPERSEDED
```

and it must NOT execute.

Payment state must remain authoritative.

The control plane must never downgrade or alter captured payment state.

---

# 30. ACTION / OUTBOX STATE CONSISTENCY

The current repository has a known semantic issue where an action can become terminal `FAILED` while its outbox remains `PENDING`.

Fix this.

Define explicit state invariants.

For example:

### Pending dispatch

```text
Action = APPROVED
Outbox = PENDING
```

### Executing

```text
Action = EXECUTING
Outbox = PROCESSING
```

### Successful execution

```text
Action = COMPLETED
Outbox = COMPLETED
```

### Retryable failure

Use a coherent non-terminal retry representation.

Do not leave:

```text
Action = FAILED
Outbox = PENDING
```

if `FAILED` is terminal.

Choose a consistent representation based on the existing state model.

If returning an action to `APPROVED` for retry, document and test it.

If introducing `RETRY_SCHEDULED`, do so deliberately and update all state-machine semantics.

Do not create contradictory lifecycle states.

---

# 31. RETRY SEMANTICS

Retries must:

* remain bounded
* use deterministic exponential backoff
* never invoke Gemini again merely because execution failed
* never re-evaluate the decision unnecessarily
* re-dispatch the same approved action
* preserve the original decision/action attribution
* maintain coherent action/outbox state

A retry must not create a brand-new AI decision unless explicitly required by a future architecture.

---

# 32. IDEMPOTENCY

Preserve deterministic idempotency.

Existing action idempotency:

```text
SHA-256
```

must remain.

Outbox idempotency must remain database-enforced.

Concurrent workers must not execute the same action twice when idempotency prevents it.

Do not weaken PostgreSQL uniqueness constraints.

---

# 33. AUDIT COMPLETENESS

Block 9 must add the minimum persistent information required to reconstruct the authoritative decision path.

The audit chain should become:

```text
Payment
    ↓
Recovery Case
    ↓
Decision Request
    ↓
Observable Context
    ↓
AI Proposal
    ↓
Policy Result
    ↓
Authorization Result
    ↓
Economic Candidate Evaluations
    ↓
Deterministic Selected Action
    ↓
Approved Action
    ↓
Execution
    ↓
Execution Result
    ↓
Later Payment Reconciliation
```

Do not persist secrets or raw chain-of-thought.

---

# 34. AI DECISION RECORD

Where the existing schema is insufficient, add appropriate migration(s).

Persist, at minimum where available and safe:

* decision ID
* case ID
* payment ID
* correlation ID
* AI provider
* model
* prompt version
* prompt hash if practical
* proposal schema/version
* sanitized context snapshot
* AI proposed action
* AI probabilities
* AI confidence
* AI rationale if allowed by project privacy rules
* uncertainty
* policy result
* policy violations/reasons
* authorization result
* deterministic candidate evaluations
* selected action
* fallback reason
* economic-engine version
* decision timestamp

Do not persist:

* API keys
* secrets
* credentials
* raw sensitive payloads unnecessarily
* chain-of-thought

---

# 35. CORRELATION ID

Correlation must be traceable across the decision lifecycle.

Where practical:

```text
webhook
→ reconciliation
→ decision request
→ AI decision
→ recovery action
→ outbox
→ execution
```

must be linkable.

At minimum ensure the durable decision record has correlation information where required for audit reconstruction.

Do not fabricate correlation IDs after the fact.

---

# 36. EVENT VERSIONING

The constitution requires versioned event contracts.

If Block 9 touches financial/domain events, add an appropriate:

```text
schema_version
```

or equivalent explicit versioning mechanism.

Do not silently break existing consumers.

Use namespaced/versioned event identifiers where this is consistent with the existing architecture.

Example concept:

```text
payment.captured.v1
recovery.case_opened.v1
recovery.decision_requested.v1
```

Do not blindly rename every existing event if compatibility would be harmed.

Inspect current event usage first.

---

# 37. FINANCIAL EVENT IMMUTABILITY

Financial events are intended to be append-only.

Strengthen this where safely possible.

Do not casually introduce a destructive migration.

Prefer appropriate database-level protection against:

```text
UPDATE
DELETE
```

on immutable financial-event records, while preserving legitimate migration/administrative mechanisms.

If full database enforcement is unsafe within this block, document precisely what remains and why.

---

# 38. RECOVERY CASE UNIQUENESS

The project intends one active recovery case per payment.

Protect this under concurrency.

Application-level:

```text
check → insert
```

is insufficient by itself.

Where appropriate, introduce a PostgreSQL partial unique index such as:

```text
one active case per payment
```

for active statuses.

Use the actual repository status values.

Do not invent statuses.

---

# 39. DATABASE CONSTRAINTS

Strengthen only the invariants relevant to this block.

Potential protections include:

* valid status values
* non-negative monetary amounts
* valid retry counts
* positive retry limits
* valid percentage ranges
* required foreign keys
* unique external payment IDs
* active recovery-case uniqueness
* decision-request uniqueness
* action/outbox idempotency

Do not attempt to encode the entire application state machine into SQL.

Keep lifecycle transition authority in deterministic application/domain code.

---

# 40. DOMAIN DEPENDENCY DIRECTION

Repository inspection identified a constitution conflict where:

```text
domain.intelligence.ai.provider
```

imports API settings/infrastructure LLM implementations.

The desired architecture is:

```text
Domain/application abstractions
        ↑
Infrastructure adapters
        ↑
FastAPI / worker composition root
```

Do not allow the domain to depend directly on FastAPI configuration or infrastructure implementation classes.

Refactor this only as far as necessary to establish the proper dependency direction without rewriting unrelated architecture.

LLM implementations such as:

* Gemini
* OpenAI-compatible
* MockLLMClient

belong in infrastructure/adapters.

The orchestration/domain layer should depend on an abstraction.

---

# 41. CONFIGURATION AND PROMPT VERSIONING

Do not perform a giant configuration redesign.

However, preserve versionability.

The AI decision should be able to identify:

* model
* prompt version
* prompt hash/content version if feasible
* agent/bundle version if feasible

Do not claim that a Python constant alone constitutes a complete version registry.

If a minimal immutable version/hash mechanism can be added safely in this block, do so.

Otherwise document the limitation.

---

# 42. SIMULATION BOUNDARY

Do not redesign simulation in this block.

Preserve:

```text
synthetic ground truth
```

strictly inside simulation/evaluation.

Production AI context must never receive:

* oracle action
* counterfactual outcome
* hidden probability
* ground-truth recovery
* World A/World B truth

Simulation may continue to use its own ground truth.

---

# 43. OBSERVABILITY

Extend observability only as necessary to expose the new pipeline.

Useful metrics include:

* decision requests pending
* decision requests processing
* decision requests failed
* decision request retries
* cases awaiting approval
* approved actions
* outbox pending
* outbox processing
* outbox failed
* action terminal failures
* superseded actions
* expired actions
* quarantined/unmatched webhook records
* approval decisions

Observability must remain:

```text
READ ONLY
```

It must never mutate production state.

---

# 44. SECURITY

Preserve existing Block 8 security boundaries.

The implementation must not weaken:

* HMAC verification
* constant-time comparisons
* webhook replay protection
* API-key protection
* secret masking
* correlation ID sanitization
* sanitized errors

Approval operations must be authenticated.

Decision workers must not expose internal errors publicly.

Do not expose:

* database credentials
* API keys
* raw secrets
* chain-of-thought
* internal stack traces

---

# 45. TEST REQUIREMENTS

This block requires meaningful tests.

Do not optimize for test count.

Test architectural behavior.

## Unit tests must cover

### Decision request

* creation
* uniqueness
* duplicate suppression
* retry
* failure
* concurrency assumptions

### Policy

* policy rejection
* cooldown
* intervention limit
* discount limits
* high-value approval requirement

### Authorization

* unauthorized action cannot execute
* pending approval cannot execute
* explicit approval permits execution

### Final action selection

* AI cannot bypass policy
* invalid AI action falls back deterministically
* deterministic economic selection is respected

### Outbox

* action + outbox atomicity
* exclusive dispatch
* retry semantics
* crash recovery
* state consistency

### Payment safety

* captured payment supersedes queued action
* authorized/captured semantics remain correct
* no recovery execution after resolution

### Amount authority

* unknown/unmatched webhook cannot create recovery economics from webhook amount
* authoritative internal order/payment amount is required

### Audit

* correlation ID persisted
* proposal preserved
* policy result preserved
* authorization preserved
* economic evaluation preserved
* selected action preserved

---

# 46. INTEGRATION TESTS

Add/modify PostgreSQL integration tests for:

```text
failed webhook
→ inbox
→ reconciliation
→ recovery case
→ decision request
→ decision worker
→ AI proposal
→ policy
→ authorization
→ action
→ outbox
→ outbox worker
→ executor
→ audit
```

Also test:

### Duplicate webhook

```text
same Razorpay event ID twice
→ one durable effect
```

### Concurrent recovery-case creation

```text
same payment concurrently processed
→ at most one active case
```

### Concurrent decision processing

```text
same decision request
→ one decision
```

### High-value action

```text
requires approval
→ no execution
→ pending approval
→ explicit approval
→ outbox
→ execution
```

### Late capture

```text
action queued
→ payment becomes CAPTURED
→ action superseded
→ no execution
```

### Outbox retry

```text
worker failure
→ retry
→ same idempotency key
→ bounded attempts
```

### Action/outbox consistency

Test every important lifecycle pair.

---

# 47. POSTGRESQL TEST REQUIREMENT

Do not claim integration tests passed unless they actually executed against PostgreSQL.

Clearly distinguish:

```text
implemented
```

from:

```text
unit tested
```

from:

```text
integration tested against live PostgreSQL
```

If PostgreSQL is unavailable:

* run all available unit tests
* run migration SQL/static validation where possible
* report that live integration verification could not be completed

Do not fabricate results.

---

# 48. GEMINI TEST ISOLATION

All automated tests must continue to use:

```text
MockLLMClient
```

No test should consume live Gemini quota.

Verify:

```text
Live Gemini calls = 0
```

where test infrastructure allows verification.

Do not weaken the existing test fixture.

---

# 49. MIGRATION SAFETY

If schema changes are required:

1. Create the next Alembic migration after `005`.
2. Keep migration history linear.
3. Make migrations reversible where practical.
4. Preserve existing data.
5. Avoid destructive changes.
6. Add indexes/constraints carefully.
7. Test migration SQL.
8. Test upgrade/downgrade where the repository supports it.
9. Consider existing rows when adding non-null fields.
10. Do not claim a migration was executed against PostgreSQL unless it actually was.

---

# 50. DO NOT IMPLEMENT THESE ITEMS IN BLOCK 9

These are explicitly outside this block:

### No frontend

Do not build the frontend/demo now.

### No multi-agent system

Do not add multiple LLM agents.

### No LangGraph/CrewAI/AutoGen/etc.

### No Redis

### No Kafka

### No Celery

### No microservices

### No real payment execution

### No real bank movement

### No live automated Razorpay charging

### No broad simulation redesign

### No unrelated refactoring

### No speculative infrastructure

### No hidden architecture changes

---

# 51. FRONTEND AND MULTI-AGENT SCOPE

The constitution historically mentions:

* frontend/demo
* multi-agent stress testing

These are known roadmap discrepancies.

Do NOT implement them in Block 9.

They will be handled as separate explicitly authorized future blocks after the authoritative recovery pipeline is stable.

---

# 52. WEBHOOK WORKER

The current repository has webhook processing functionality but no equivalent continuously running webhook-worker daemon comparable to the outbox worker.

Do not automatically build a large worker framework.

For Block 9, ensure the architecture supports a durable decision handoff after reconciliation.

If a minimal worker/scheduler is required for decision requests, implement it consistently with the existing worker style.

Do not create a new distributed infrastructure layer.

---

# 53. API BEHAVIOR

If orchestration becomes asynchronous:

Do not preserve an API contract that falsely implies:

```text
request → immediate action execution
```

where that is no longer true.

Return an appropriate durable status such as:

```text
decision requested
```

or:

```text
action persisted
```

depending on the existing API design.

Do not claim execution completed merely because an outbox event was created.

---

# 54. EXISTING TEST COMPATIBILITY

Current unit tests previously reached approximately:

```text
256 passed
```

after Block 8.

Do not assume that exact number remains unchanged.

After modifications:

* update tests whose expected behavior is intentionally changed
* add new tests
* run the full unit suite
* report exact results

Do not delete tests merely to make the suite pass.

Do not weaken assertions.

---

# 55. IMPLEMENTATION STYLE

Prefer:

```text
minimal
targeted
architecturally coherent
```

changes.

Do not rewrite the entire repository.

Reuse existing:

* models
* validators
* EconomicEngine
* orchestrator
* control plane
* outbox
* state machines
* settings
* test fixtures

where appropriate.

Do not duplicate business logic.

---

# 56. DOCUMENTATION

Update relevant documentation to reflect the actual implementation.

At minimum review:

```text
docs/PROJECT_CONTEXT.md
docs/PROJECT_CONSTITUTION.md
docs/OBSERVABILITY_AND_EVALUATION.md
docs/PRODUCTION_OPERATIONS.md
```

Do NOT casually modify the constitution's architectural principles to make implementation appear compliant.

If implementation intentionally diverges from the constitution, stop and report it rather than rewriting the rule.

Documentation must describe reality.

---

# 57. REQUIRED ARCHITECTURAL INVARIANTS

Before declaring Block 9 complete, verify these invariants:

### Invariant 1

A verified failed payment can eventually reach decision orchestration through a durable asynchronous handoff.

### Invariant 2

Webhook processing does not synchronously call an LLM.

### Invariant 3

An unmatched webhook amount cannot become authoritative recovery economics.

### Invariant 4

AI remains proposal-only.

### Invariant 5

Policy is deterministic and mandatory.

### Invariant 6

High-value approval is an actual execution gate.

### Invariant 7

Final executable action cannot bypass deterministic policy/economic selection.

### Invariant 8

Only approved actions can reach execution.

### Invariant 9

Only the outbox worker dispatches actions.

### Invariant 10

Action + action-outbox creation is atomic.

### Invariant 11

Late payment capture supersedes queued recovery work.

### Invariant 12

Retries do not invoke AI again.

### Invariant 13

Action/outbox lifecycle states remain coherent.

### Invariant 14

Financial state is still controlled exclusively by reconciliation.

### Invariant 15

All money remains integer minor units.

### Invariant 16

AI/simulation ground truth remains isolated.

### Invariant 17

Decision audit records preserve proposal vs selected action.

### Invariant 18

Correlation IDs allow durable decision tracing.

### Invariant 19

PostgreSQL remains the persistence authority.

### Invariant 20

No real financial money movement occurs.

---

# 58. REQUIRED FINAL VERIFICATION

After implementation, run as many of these as the environment permits:

```powershell
.\.venv\Scripts\alembic upgrade head
```

```powershell
.\.venv\Scripts\python -m pytest tests/unit/ -v
```

```powershell
.\.venv\Scripts\python -m pytest tests/unit/ -o addopts="" -v
```

```powershell
.\.venv\Scripts\python -m pytest -m integration -v
```

If PostgreSQL is unavailable, do NOT pretend integration passed.

Also run relevant targeted tests for the new Block 9 functionality.

---

# 59. FINAL IMPLEMENTATION REPORT

When implementation is complete, provide a detailed completion report.

The report must include:

## A. Executive Summary

What was implemented.

## B. Files Created

Exact files.

## C. Files Modified

Exact files.

## D. Architecture Changes

Explain the actual runtime flow after Block 9.

## E. Database Changes

Explain migrations, tables, indexes, constraints, and transaction behavior.

## F. Decision Request Pipeline

Explain how:

```text
case → decision request → orchestration
```

now works.

## G. Policy & Authorization

Explain exactly how approval is enforced.

## H. Final Action Selection

Explain exactly how AI proposal differs from deterministic final selection.

## I. Outbox

Explain why the outbox is now the exclusive dispatch mechanism.

## J. Retry Semantics

Explain exact state transitions.

## K. Payment Safety

Explain how payment capture authority remains with webhook reconciliation.

## L. Amount Authority

Explain how unmatched webhook amounts are handled.

## M. Auditability

Explain exactly what is now persisted.

## N. Security

Explain relevant security protections.

## O. Tests

Report exact commands and exact results.

Clearly separate:

```text
unit tests passed
```

from:

```text
integration tests implemented
```

from:

```text
integration tests actually executed against PostgreSQL
```

## P. Gemini Usage

Report:

```text
Live Gemini API calls:
Live Gemini tokens:
```

Do not guess.

## Q. Remaining Limitations

Be honest about anything that remains incomplete.

## R. Constitution Alignment

Identify any remaining discrepancies.

## S. STOP

After providing the implementation completion report:

**STOP.**

Do NOT perform an independent audit.

Do NOT start Block 10.

Do NOT implement frontend.

Do NOT implement multi-agent stress testing.

Do NOT make additional unsolicited changes.

---

# 60. MOST IMPORTANT FINAL INSTRUCTION

The purpose of Block 9 is **not** to make the project look complete.

The purpose is to make the **actual runtime authority chain correct**.

The target architecture is:

```text
                         ┌──────────────────────┐
                         │   Razorpay Event     │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Webhook Verification │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │   Durable Inbox      │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │    Reconciliation    │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │   Recovery Case      │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Durable Decision Req │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Decision Orchestrator│
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │     AI Proposal      │
                         │   NON-AUTHORITATIVE  │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Deterministic Policy │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │    Authorization     │
                         │   / Human Approval   │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │   Economic Engine    │
                         │    DETERMINISTIC     │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Final Selected Action│
                         └──────────┬───────────┘
                                    ↓
                    ┌──────────────────────────────┐
                    │ Approved Action + Outbox     │
                    │      SAME TRANSACTION        │
                    └──────────────┬───────────────┘
                                   ↓
                         PostgreSQL COMMIT
                                   ↓
                    ┌──────────────────────────────┐
                    │      Outbox Worker            │
                    │ EXCLUSIVE DISPATCH AUTHORITY  │
                    └──────────────┬───────────────┘
                                   ↓
                         ┌──────────────────────┐
                         │    Control Plane     │
                         │ Final Safety Checks  │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Test-Mode Executor   │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Execution / Audit    │
                         └──────────┬───────────┘
                                    ↓
                         ┌──────────────────────┐
                         │ Later Razorpay Event │
                         │  Authoritative State │
                         └──────────────────────┘
```

The fundamental philosophy remains:

> **We are NOT building an AI that controls payments.**

We are building:

> **a financially safe, deterministic payment-recovery decision system in which AI is one bounded proposal component inside a larger authoritative architecture.**

Implement Block 9 accordingly.

**Implementation first. Audit later.**

**STOP after the implementation completion report.**

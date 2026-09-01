# Financial Agent Lab — Project Constitution

> **Status:** AUTHORITATIVE  
> **Version:** 1.0  
> **Established:** 2026-08-30  
> **Audience:** Every engineer, AI agent, and implementation task operating in this repository.  
> **Authority:** This document is the engineering contract. It is not advisory. Deviations require explicit architectural approval and must be documented.

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [Product Thesis](#2-product-thesis)
3. [MVP Boundary](#3-mvp-boundary)
4. [Architectural Principles](#4-architectural-principles)
5. [Domain Boundaries](#5-domain-boundaries)
6. [AI vs Deterministic Responsibilities](#6-ai-vs-deterministic-responsibilities)
7. [Financial Safety Rules](#7-financial-safety-rules)
8. [Event and Webhook Principles](#8-event-and-webhook-principles)
9. [Simulation Principles](#9-simulation-principles)
10. [Evaluation Principles](#10-evaluation-principles)
11. [Technology Selection Principles](#11-technology-selection-principles)
12. [Security Principles](#12-security-principles)
13. [Testing Principles](#13-testing-principles)
14. [Observability Principles](#14-observability-principles)
15. [Development Workflow](#15-development-workflow)
16. [Future Scalability Principles](#16-future-scalability-principles)
17. [Explicit Anti-Patterns](#17-explicit-anti-patterns)
18. [Questions Every Future Implementation Must Answer](#18-questions-every-future-implementation-must-answer)

---

## 1. Project Purpose

**Financial Agent Lab** is a fintech/AI engineering prototype built for the Razorpay AI Buildathon.

Its purpose is to demonstrate that autonomous financial agents can be built with economic rigor, safety, and independent verifiability — not merely AI novelty.

The lab answers a question that matters to every revenue-critical business:

> *"When a payment is at risk, should the system intervene at all — and if it does, which action maximizes net incremental revenue?"*

The system must reason under uncertainty, respect financial constraints, and produce decisions that can be audited, replayed, and compared against credible baselines.

---

## 2. Product Thesis

**Core thesis:** Build a Financial Agent Simulation & Decision Lab that evaluates whether autonomous financial agents make economically sound decisions under realistic and adversarial conditions.

**First product wedge:** Incremental Revenue Recovery  
**MVP scenario:** Payment degradation / failed one-time payment recovery

**Primary metric:** Net Incremental Revenue — not recovery rate in isolation.

Net Incremental Revenue is defined as:

```
Net Incremental Revenue =
    Revenue recovered WITH intervention
  - Revenue that would have recovered WITHOUT intervention   (counterfactual baseline)
  - Cost of intervention actions
  - Cost of unnecessary interventions on payments that would have self-recovered
```

This metric is the single most important output of the system. Every design decision must be evaluated against its ability to produce a credible, honest estimate of this metric.

---

## 3. MVP Boundary

The MVP is strictly bounded. It covers:

### In scope

| Capability | Description |
|---|---|
| Payment event ingestion | Receive and persist Razorpay webhook events (Test Mode only) |
| Failure classification | Classify failed/at-risk payments by type, amount, customer signal |
| Recovery action catalogue | WAIT, RETRY, PAYMENT_LINK, CUSTOMER_NOTIFICATION, ESCALATE |
| Policy validation layer | Deterministic rules that constrain permissible actions |
| Economic decision engine | Calculate expected net incremental value per candidate action |
| AI reasoning agent | One LLM reasoning over context and selecting from permitted actions |
| Simulation / Digital Twin | Synthetic payment population with controlled ground truth |
| Counterfactual engine | Estimate baseline recovery without intervention |
| Evaluation lab | Compare no-intervention, rule baseline, naive AI, economic AI |
| Observability trail | Full decision trace from context to action to outcome to evaluation |
| Frontend lab UI | Visualise scenarios, decisions, metrics, and traces |

### Out of scope for MVP

- Real merchant money movement
- Production Razorpay live mode
- Subscription / recurring billing scenarios
- Multi-currency operations
- Fraud detection
- Credit decisioning
- Consumer-facing interfaces
- Multi-tenant SaaS

---

## 4. Architectural Principles

These principles are permanently binding. They are numbered for reference in future implementation tasks.

### P-01 — Financial Correctness Over AI Cleverness

Economic soundness is the primary quality attribute of this system. A technically impressive AI that produces financially incorrect or unsafe outputs has failed the core objective.

Financial correctness is always prioritised over:
- AI capability demonstration
- engineering elegance
- performance optimisation
- developer convenience

### P-02 — AI Is a Reasoning Component, Not the Financial Authority

The AI component exists to reason over ambiguous, heterogeneous context and to select from a set of pre-validated, policy-constrained candidate actions.

**The AI may:**
- Interpret payment failure context
- Diagnose ambiguous failure type
- Generate and rank candidate actions
- Reason over customer behaviour patterns
- Provide structured explanations for decisions

**The AI may NOT:**
- Directly execute financial operations
- Override policy validation outcomes
- Calculate authoritative monetary amounts
- Change system financial state without deterministic validation
- Bypass authorization controls

### P-03 — Deterministic Financial Control Layer

Every financial action passes through a deterministic control layer before execution. This is non-negotiable.

The required execution path is:

```
AI DECISION
    |
    v
Policy Validation  (deterministic, independently testable)
    |
    v
Authorization Check  (deterministic)
    |
    v
Economic Calculation  (deterministic, integer arithmetic)
    |
    v
State Validation  (deterministic)
    |
    v
Idempotency Check  (deterministic)
    |
    v
EXECUTION
```

The path `AI -> DIRECT FINANCIAL ACTION` is **permanently forbidden** in this codebase.

### P-04 — Real Razorpay vs Synthetic Simulation

The system maintains a hard boundary between:

| Layer | Description |
|---|---|
| **Real Razorpay Test Mode** | Actual Razorpay Test API, actual webhook events, no real money |
| **Synthetic Simulation** | Our synthetic payment population and digital twin |
| **Decision / Evaluation Logic** | Our proprietary reasoning and metric calculation |

Rules:
- Never claim synthetic simulation data is real Razorpay merchant data.
- Never invent Razorpay API capabilities not documented in the official API reference.
- Never assume undocumented Razorpay behaviour.
- Always clearly label synthetic data as synthetic in all interfaces.

### P-05 — Counterfactual Honesty

The system estimates what would have happened without intervention. This is a simulation estimate, not a causal proof.

**Always distinguish:**
- `observed_outcome` — what actually happened in this case
- `simulated_outcome` — what the simulation model says happened
- `estimated_counterfactual` — the baseline outcome estimate without intervention
- `estimated_incremental_value` — the difference, attributed to intervention

**Never claim causal impact** unless the evaluation methodology actually supports causal inference (e.g. randomised holdout). The MVP uses simulation-based estimation; this must be stated clearly in all outputs.

### P-06 — Event-Driven Thinking

Financial events are durable state transitions. They must be persisted reliably.

**MVP event processing stack:**
- PostgreSQL (primary source of truth)
- Transactional inbox/outbox pattern
- Background worker for async processing

Do not introduce Kafka for architectural appearance. The architecture must, however, preserve a clean migration path to a durable streaming platform should production scale require it — meaning domain event schemas must be cleanly defined and not tightly coupled to the webhook transport format.

### P-07 — Modularity Without Premature Microservices

Use clear domain module boundaries. Modules should be independently testable and have minimal coupling.

Do not split into separate deployable services unless:
- Independent deployment is concretely required
- Independent scaling is concretely required
- Separate team ownership is concretely required

The MVP is a single deployable system with clear internal domain boundaries.

### P-08 — PostgreSQL as Source of Truth

PostgreSQL is the authoritative persistent financial datastore.

- All durable financial state lives in PostgreSQL.
- Redis, if introduced, serves as a cache or coordination mechanism only. It is never the authoritative record for any financial state.
- Financial decisions must remain consistent even if Redis is unavailable.

### P-09 — Reproducible Simulation

Simulation is a first-class engineering concern, not a demo fixture.

All simulation scenarios must support:
- Deterministic seeds (reproducible with the same seed)
- Replay (run the same scenario again and get the same result)
- Known ground truth (the correct answer is known when evaluating)
- Controlled randomness (configurable noise, configurable failure rates)
- Scenario versioning (scenarios can be compared across agent versions)

### P-10 — Evaluation Is a First-Class System

Evaluation is not a dashboard afterthought. It is core product.

The evaluation system must compare at minimum:
- **No intervention baseline** — do nothing, observe natural recovery
- **Deterministic rule baseline** — simple rules (e.g., always retry once)
- **Naive AI baseline** — LLM without economic constraint
- **Economic decision agent** — our full system

Required metrics:
- Gross recovery rate
- Net incremental revenue
- Incremental recovery rate (vs counterfactual)
- Unnecessary intervention rate (intervened on self-recovering payments)
- Missed recovery rate (failed to intervene on recoverable payments)
- Policy violation count
- Decision latency (P50, P95)
- Agent inference cost per decision

### P-11 — Security by Design

Security controls are not optional enhancements. They are required from the first implementation. See Section 12.

### P-12 — Webhook Safety

Webhooks are untrusted external inputs. See Section 8.

### P-13 — Observability

Every important financial decision must be traceable end-to-end. See Section 14.

### P-14 — AI Outputs Must Be Structured

Agent decisions must use typed schemas. Free-form natural language is acceptable for human-readable explanation fields only. It is not acceptable as the machine-readable decision record.

Every agent decision must produce a structured record including at minimum:
- `decision_id` — unique identifier
- `agent_version` — which agent produced this decision
- `action` — the selected action from the permitted catalogue
- `confidence` — agent's stated confidence (0-1)
- `reasoning` — human-readable explanation (string)
- `candidate_actions` — all actions considered with expected values
- `policy_result` — deterministic policy validation outcome
- `created_at` — timestamp

### P-15 — No Technology for Buzzword Value

Every technology choice must be justified by a concrete, stated requirement. When evaluating a technology, the question is:

> *"What specific problem would we have without this, and why does no simpler existing component solve it?"*

If that question cannot be answered concretely, the technology is not introduced.

### P-16 — Prefer Simple, Production-Minded Engineering

Initial technology preferences (not permission to implement everything now):

| Concern | Technology |
|---|---|
| Frontend | Next.js + TypeScript |
| Backend | FastAPI + Python |
| Database | PostgreSQL |
| Async processing | Background worker (APScheduler or similar) |
| Cache / coordination | Redis only where explicitly justified |
| AI / LLM | One strong model via its direct SDK (initially) |
| Simulation | Python |
| Financial logic | Deterministic Python domain services |
| Containerisation | Docker |
| Testing | pytest |

### P-17 — Domain Logic Must Be Framework-Independent

Core financial and simulation logic must not import or depend on:
- FastAPI or any web framework
- LLM SDKs
- Frontend code
- Raw Razorpay HTTP clients

Domain services are importable, runnable, and testable without any external framework being initialised.

### P-18 — External Integrations Behind Adapters

Razorpay API calls are isolated behind an integration adapter boundary. The core domain calls adapter interfaces; it does not call Razorpay HTTP endpoints directly.

This enables:
- Swapping real Razorpay for a test double without changing domain code
- Testing domain logic in complete isolation
- Controlled upgrade if Razorpay API changes

### P-19 — Agent Versioning

Agent prompts, system instructions, tool definitions, and decision configuration are versionable artefacts. Every agent decision record must reference the agent version that produced it. Evaluation results are meaningless without this reference.

### P-20 — Build Vertically

Implementation proceeds one vertical block at a time. Do not implement future blocks while working on an earlier block unless explicitly instructed by architectural direction.

**Build sequence:**

| Block | Scope |
|---|---|
| Block 1 | Financial core + payment/recovery domain |
| Block 2 | Razorpay Test Mode integration + webhook processing |
| Block 3 | Simulation / Digital Twin |
| Block 4 | Economic + Counterfactual Engine |
| Block 5 | AI Recovery Agent |
| Block 6 | Evaluation Lab |
| Block 7 | Frontend / Demo |
| Block 8 | Multi-Agent Stress Testing |

---

## 5. Domain Boundaries

The system is organised into the following domain modules. Each module owns its data and exposes interfaces — it does not grant other modules direct database access into its tables.

```
+-------------------------------------------------------------+
|                    Financial Agent Lab                       |
|                                                             |
|  +------------------+   +--------------------------------+  |
|  |  Payment Domain  |   |      Simulation Domain         |  |
|  |                  |   |                                |  |
|  |  - Payment       |   |  - ScenarioGenerator           |  |
|  |  - PaymentEvent  |   |  - SyntheticPaymentPopulation  |  |
|  |  - RecoveryCase  |   |  - DigitalTwin                 |  |
|  |  - ActionRecord  |   |  - CounterfactualEstimator     |  |
|  +--------+---------+   +---------------+----------------+  |
|           |                             |                   |
|  +--------v-----------------------------v-----------------+  |
|  |            Financial Control Domain                     |  |
|  |                                                         |  |
|  |  - PolicyValidator (deterministic)                      |  |
|  |  - AuthorizationService (deterministic)                 |  |
|  |  - EconomicCalculator (deterministic, integer units)    |  |
|  |  - IdempotencyService (deterministic)                   |  |
|  |  - ActionCatalogue (WAIT/RETRY/LINK/NOTIFY/ESCALATE)    |  |
|  +-------------------------+---------------------------------+  |
|                            |                                |
|  +-------------------------v---------------------------------+  |
|  |                    Agent Domain                          |  |
|  |                                                         |  |
|  |  - RecoveryAgent (AI reasoning, structured output)      |  |
|  |  - AgentVersionRegistry                                 |  |
|  |  - DecisionRecord (typed schema)                        |  |
|  +-------------------------+---------------------------------+  |
|                            |                                |
|  +-------------------------v---------------------------------+  |
|  |                 Evaluation Domain                        |  |
|  |                                                         |  |
|  |  - EvaluationRun                                        |  |
|  |  - MetricCalculator                                     |  |
|  |  - BaselineComparator                                   |  |
|  |  - ReportGenerator                                      |  |
|  +-------------------------+---------------------------------+  |
|                            |                                |
|  +-------------------------v---------------------------------+  |
|  |          Integration Adapters (Boundary)                 |  |
|  |                                                         |  |
|  |  - RazorpayAdapter (wraps real Razorpay Test API)       |  |
|  |  - WebhookIngestionService                              |  |
|  +----------------------------------------------------------+  |
|                                                             |
|  +----------------------------------------------------------+  |
|  |              Infrastructure Layer                        |  |
|  |                                                         |  |
|  |  - PostgreSQL (source of truth)                         |  |
|  |  - Outbox/Inbox tables                                  |  |
|  |  - Background worker                                    |  |
|  |  - Redis (cache/coordination only, if justified)        |  |
|  +----------------------------------------------------------+  |
+-------------------------------------------------------------+
```

**Module ownership rules:**
- No module may access another module's database tables directly.
- Cross-module communication is via defined service interfaces or domain events.
- Integration Adapters are the only code that makes external HTTP calls.
- Domain logic never imports from the Integration Adapter layer.

---

## 6. AI vs Deterministic Responsibilities

This is the most critical architectural boundary in the system.

### Deterministic Layer — must always be deterministic

| Responsibility | Why |
|---|---|
| Monetary arithmetic | Correctness, reproducibility, auditability |
| Currency representation | Precision — no floating-point |
| Policy limit enforcement | Safety, compliance |
| Action authorisation | Security |
| State transition validation | Consistency |
| Idempotency enforcement | Reliability |
| External API execution | Safety — one action, once |
| Evaluation metric calculation | Scientific validity |
| Webhook signature verification | Security |
| Outbox/inbox processing | Reliability |

### AI Layer — permitted scope

| Responsibility | Why AI is appropriate |
|---|---|
| Interpret payment failure context | Heterogeneous, unstructured signal |
| Diagnose ambiguous failure type | Pattern in noisy data |
| Generate candidate recovery actions | Creative enumeration over context |
| Rank candidates by reasoning | Contextual judgement |
| Explain decision in natural language | Communication |
| Estimate customer behavioural risk | Probabilistic inference |

### The Handoff Contract

1. Deterministic code assembles a structured `DecisionContext` (all financial facts, policy limits, permitted actions catalogue, customer signals).
2. `DecisionContext` is passed to the agent.
3. Agent returns a structured `DecisionOutput` (selected action, reasoning, confidence, candidates with expected values).
4. Deterministic code validates `DecisionOutput` against policy — the AI's selected action is re-validated independently.
5. Deterministic code executes the action if validation passes.
6. All steps are written to the audit log under one `decision_id`.

The AI never touches execution. The deterministic layer never skips validation because the AI said so.

---

## 7. Financial Safety Rules

These rules are permanent constraints. They cannot be relaxed without architectural approval.

### FS-01 — Integer Minor Units for Money

All monetary values in financial calculations, database storage, and inter-service communication are represented as **integer minor units** (e.g. paise for INR).

```python
# CORRECT
amount_paise: int = 125050   # Rs. 1,250.50

# FORBIDDEN
amount_rupees: float = 1250.50   # floating-point monetary value
```

Human-readable formatting (e.g. "Rs. 1,250.50") is performed only at the presentation layer, never stored or used in calculations.

### FS-02 — No LLM Financial Arithmetic

The AI may not be asked to compute, verify, or validate monetary amounts. It may reference amounts in its reasoning text but has no authority over their correctness.

### FS-03 — All Actions Are Idempotent

Every recovery action execution must be idempotent. Given the same `case_id` + `action_type`, executing twice must produce the same observable outcome as executing once.

Idempotency keys must be generated deterministically and persisted before action execution.

### FS-04 — One Action Per Case at a Time

A single recovery case may not have two concurrent actions executing simultaneously. The system must enforce serialisation at the case level.

### FS-05 — Policy Validation Is Not Optional

No action may be executed without passing deterministic policy validation. Policy validation is not a suggestion to the AI — it is a gate on execution. If validation fails, the action does not execute, regardless of AI confidence.

### FS-06 — State Machines Are Explicit

Payment and case state transitions follow explicit, documented state machines. Arbitrary transitions are rejected. Every state transition is logged with a timestamp and cause.

### FS-07 — Audit Log Is Append-Only

The financial audit log is append-only. No record may be deleted or updated. Corrections are recorded as new entries that reference and supersede prior entries.

### FS-08 — Never Trust Webhook Payload for Financial Amounts

Financial amounts referenced in business logic must be sourced from our own database records, not blindly trusted from incoming webhook payloads. Webhook amounts may be used to detect discrepancies, triggering investigation — they are not authoritative.

---

## 8. Event and Webhook Principles

### Webhook Processing Rules

1. **Verify first.** Every incoming Razorpay webhook must have its signature verified before any processing begins. Reject unverified requests with HTTP 400.

2. **Persist immediately.** The raw webhook event is written to the database in the same transaction as acknowledgement. If persistence fails, return HTTP 500 — do not acknowledge events that were not persisted.

3. **Acknowledge fast.** Return HTTP 200 within a strict time budget (target: < 2 seconds). No business logic executes inside the webhook request handler.

4. **Process asynchronously.** Business logic is executed by a background worker that reads from the inbox table. The webhook handler only writes to the inbox.

5. **Handle duplicates.** Razorpay may deliver the same event more than once. The inbox table uses the Razorpay event ID as a unique key. Duplicate delivery is a no-op, not an error.

6. **Handle out-of-order delivery.** Events may arrive out of sequence. The system applies events based on event timestamps and sequence numbers, not arrival order.

7. **Idempotent processing.** The inbox worker marks events as processed after successful handling. A crash mid-processing results in reprocessing from the beginning — all handlers must be safe to run multiple times.

### Outbox Pattern

Domain events produced by business logic are written to an outbox table within the same database transaction as the state change they represent. A background worker reads the outbox and delivers events to downstream consumers. This guarantees at-least-once delivery without distributed transaction complexity.

### Event Schema

All domain events must have:
- `event_id` — UUID, globally unique
- `event_type` — namespaced string (e.g. `payment.failed`, `recovery.action.executed`)
- `aggregate_id` — the ID of the entity this event belongs to
- `aggregate_type` — the entity type
- `payload` — typed JSON schema
- `schema_version` — event schema version
- `created_at` — timestamp (UTC)
- `correlation_id` — traces a chain of related events

---

## 9. Simulation Principles

### Why Simulation Matters

The counterfactual cannot be observed in a live system without a randomised holdout. Simulation allows us to build a controlled environment where:
- Ground truth is known
- Counterfactuals can be computed exactly
- Edge cases can be stress-tested
- Agent versions can be compared fairly

### Simulation Requirements

1. **Deterministic seeds.** Every simulation run accepts a `seed` parameter. Given the same seed and scenario version, the run is byte-for-byte reproducible.

2. **Scenario versioning.** Scenarios are identified by name and version. Evaluation results must reference the scenario version.

3. **Synthetic data labelling.** All synthetic payments carry a clear marker (`data_source: synthetic`). They are never mixed with real Razorpay data in the same evaluation run.

4. **Ground truth.** Each synthetic payment case has a known ground truth counterfactual — what the payment would have done without intervention. This is the correct answer the evaluation is measured against.

5. **Controlled noise.** Simulation parameters (failure rates, customer behaviour distributions, recovery probabilities) are configurable inputs, not hardcoded constants.

6. **Digital Twin.** The simulation includes a model of the payment processor that can simulate retry outcomes, customer response to notifications, and natural payment recovery — without calling the real Razorpay API.

7. **No real money.** Simulation never initiates real payment operations. The simulation's Digital Twin handles all "execution" results internally.

---

## 10. Evaluation Principles

### Scientific Validity

The evaluation system is the ground truth for whether the agent works. It must be held to scientific standards:

- Metrics are defined before evaluation runs, not chosen post-hoc.
- Baselines are implemented correctly before the agent is evaluated.
- Evaluation runs are reproducible from the same seed.
- Results reference the exact agent version, scenario version, and simulation seed.
- No cherry-picking of runs or scenarios.

### Required Baselines

| Baseline | Description |
|---|---|
| `no_intervention` | Never act. Observe natural recovery. This is the counterfactual floor. |
| `rule_deterministic` | Simple deterministic rules (e.g. always retry once for amounts below threshold) |
| `naive_ai` | LLM with context but without economic constraint or policy validation |
| `economic_agent` | Full system: economic calculation + policy + AI reasoning |

### Required Metrics (per evaluation run)

| Metric | Definition |
|---|---|
| `gross_recovery_rate` | (Cases recovered) / (Total at-risk cases) |
| `gross_recovery_revenue` | Total revenue recovered |
| `estimated_counterfactual_recovery` | Revenue that would have recovered without intervention |
| `net_incremental_revenue` | gross_recovery_revenue - counterfactual_recovery - action_costs |
| `unnecessary_intervention_rate` | Interventions on cases that would have self-recovered |
| `missed_recovery_rate` | Cases that could have been recovered but were not acted on |
| `policy_violation_count` | Actions attempted that failed policy validation |
| `decision_latency_p50` | Median time from event to decision |
| `decision_latency_p95` | P95 time from event to decision |
| `agent_cost_per_decision` | LLM inference cost per decision |

### Evaluation Integrity Rules

- Evaluation code does not share logic with the agent. They are separate modules.
- The evaluator has access to ground truth; the agent does not.
- Evaluation runs are logged and cannot be silently re-run to improve scores.

---

## 11. Technology Selection Principles

### Evaluation Criteria for New Technology

Before introducing any new library, service, or framework, the following questions must be answered in writing (as a comment in the PR or relevant ticket):

1. What specific problem does this solve?
2. What is the simplest alternative that does not introduce this technology?
3. Why is the alternative insufficient?
4. What is the operational cost of this technology (setup, maintenance, failure modes)?
5. Is this justified at MVP scale, or is it future architecture?

### Technology Preferences (Initial)

See P-16. These are the preferred initial choices. They must not all be implemented at once — they are introduced block-by-block as concrete requirements arise.

### Technology Constraints

The following technologies must NOT be introduced without explicit architectural approval with written justification:

- Kafka or any distributed message broker
- Kubernetes or any container orchestration platform
- Vector databases (Pinecone, Weaviate, Qdrant, etc.)
- Feature stores (Feast, Tecton, etc.)
- Multiple LLMs running concurrently
- Complex agent orchestration frameworks (LangGraph, CrewAI, AutoGen, etc.) as primary agent architecture
- Multiple separate deployable microservices

---

## 12. Security Principles

### Credential Management

- **Never commit** API keys, secrets, database credentials, or webhook signing secrets to version control.
- All secrets are loaded from environment variables or a secrets manager.
- `.env` files are listed in `.gitignore` and never committed.
- The repository includes a `.env.example` with placeholder values only.

### API Security

- All backend endpoints require authentication (to be specified per endpoint in Block implementation).
- Razorpay webhook endpoints verify webhook signatures on every request using HMAC-SHA256.
- Input validation is applied to all external inputs before processing.

### Least Privilege

- The database user used by the application has only the minimum required permissions.
- LLM API keys are backend-only. They are never exposed to the frontend.
- Razorpay secret keys are backend-only. They are never exposed to the frontend.

### Frontend Security

- The frontend receives only data it needs to render.
- No credentials, secret keys, or raw financial records are sent to the frontend unless required and explicitly scoped.
- API responses are never proxied to the frontend without sanitisation.

### Audit Logging

- All security-relevant events are logged: authentication, authorisation failures, webhook signature failures, policy violations.
- Audit logs include timestamp, actor, action, and outcome.

---

## 13. Testing Principles

### Test Pyramid

```
          [E2E / Integration Tests]        <- few, cover critical paths
         [Domain Integration Tests]        <- moderate, cover domain interactions
      [Unit Tests -- Domain Services]      <- many, fast, pure functions, no I/O
```

### Rules

1. **Domain logic is tested without frameworks.** Core financial, policy, and economic logic is tested with plain pytest — no FastAPI test client, no database, no LLM calls.

2. **Simulation has deterministic tests.** Given a fixed seed and scenario, simulation output is asserted exactly.

3. **Policy validation is exhaustively tested.** Every policy boundary condition must have a test: at-limit, just-below-limit, just-above-limit.

4. **Evaluation metrics are tested against known inputs.** The metric calculator must be tested with manually constructed cases where the correct output is known.

5. **Agent decisions are tested with test doubles.** LLM calls in tests use deterministic stubs, not real API calls.

6. **Idempotency is tested by design.** Every action handler has a test that executes it twice and asserts the outcome is the same as executing once.

7. **Webhook processing tests cover:** valid signature, invalid signature, duplicate delivery, out-of-order delivery, malformed payload.

### Test File Structure

Tests live in a `tests/` directory mirroring the source structure. A test for `src/financial_core/policy_validator.py` lives at `tests/financial_core/test_policy_validator.py`.

---

## 14. Observability Principles

### Every Decision Is a Traceable Event

Each financial recovery decision must produce a complete, durable trace. The trace is not optional logging — it is a first-class system output.

### Required Trace Record (per decision)

```
decision_id          -> globally unique identifier
case_id              -> the recovery case this decision belongs to
correlation_id       -> trace across the full event chain
agent_version        -> which agent version made this decision
context_snapshot     -> all inputs the agent received (serialised)
candidate_actions    -> all actions considered, with expected values
policy_validation    -> result of deterministic policy check
selected_action      -> what was decided
action_execution     -> result of executing the action (success/failure, external reference)
state_transition     -> the state change that resulted
outcome              -> observed outcome (if known)
evaluation_result    -> incremental value attribution (if evaluated)
timestamps           -> created_at at each stage
```

### Logging

- Structured logging only (JSON lines). No unstructured string-concatenated logs in production.
- Every log record includes: `correlation_id`, `decision_id` where applicable, `level`, `timestamp`, `service`, `message`.
- Log levels are used correctly: DEBUG for verbose development, INFO for normal operations, WARNING for degraded but recoverable, ERROR for failures requiring attention.

### Alerting Surface

The following conditions must be observable and alertable (even in MVP, via log queries):
- Policy violation
- Webhook signature failure
- Action execution failure (external API error)
- Background worker stall
- Agent decision latency exceeding threshold

---

## 15. Development Workflow

### Branch Strategy

- `main` — production-ready, protected
- `develop` — integration branch
- Feature branches from `develop`, named `block-N/description` or `feature/description`

### Implementation Block Discipline

When implementing a block:
1. Confirm the block scope with the current task description before writing code.
2. Do not implement any component from a future block as a side effect.
3. Each block must pass its own tests before the next block begins.
4. Block completion is marked by a committed, passing test suite — not by "the code is written".

### Environment Management

- Python: use `venv` or equivalent per the project's declared tooling.
- Node.js: use `npm` with a committed `package-lock.json`.
- All dependencies are pinned with exact versions in lock files.
- Dependency updates are deliberate, not incidental.

### Configuration

- All configurable values (thresholds, limits, timeouts, feature flags) are loaded from configuration, not hardcoded in domain logic.
- Configuration has documented defaults.
- Configuration is validated at application startup.

### Documentation

- Every module has a module-level docstring explaining its responsibility and what it does NOT do.
- Every public function has a docstring with parameters, return values, and exceptions.
- Architectural decisions with non-obvious rationale are documented with an inline comment referencing the relevant principle (e.g. `# P-03: passes through deterministic control layer`).

---

## 16. Future Scalability Principles

The MVP architecture must not require a complete rewrite to scale. The following forward-compatibility requirements apply from the start:

### Event Schema Forward-Compatibility

Domain events are versioned. The consumer must handle unknown fields gracefully (ignore, do not error).

### Streaming Migration Path

The outbox/inbox pattern means the domain event stream can be consumed by Kafka/Pulsar by simply adding a Kafka producer to the outbox worker. Domain logic does not change.

### Service Extraction Path

Modules with clear boundaries can be extracted into separately deployable services. For this to remain feasible:
- No module directly queries another module's database tables.
- Cross-module calls go through service interfaces that can later become HTTP/gRPC calls.

### Agent Versioning for Reproducibility

Agent version references in decision records mean any past decision can be re-evaluated with a newer agent version, enabling longitudinal comparison.

### Horizontal Worker Scaling

The background worker is designed to be safely run as multiple instances. Processing uses optimistic locking or `SELECT FOR UPDATE SKIP LOCKED` to prevent duplicate processing.

### Data Volume Anticipation

- Payment and event tables will grow unboundedly. Partition strategy (by date) should be planned before volume makes it painful.
- Evaluation run results are stored with their full context — archival/compression strategy should be considered at Block 6.

---

## 17. Explicit Anti-Patterns

These patterns are forbidden. If encountered in a code review or implementation, they must be corrected.

| Anti-Pattern | Why Forbidden |
|---|---|
| `amount: float = 1250.50` for monetary values | Floating-point imprecision in financial calculations |
| LLM asked to calculate the refund amount or any monetary value | AI performing authoritative financial arithmetic |
| Razorpay client called directly from domain service | Tight coupling, bypasses adapter boundary |
| AI output used to skip or short-circuit policy validation | AI overriding deterministic policy gate |
| `RAZORPAY_KEY_SECRET` in frontend environment variable | Secret key exposure |
| Webhook handler that sleeps, calls external APIs, or runs heavy logic | Slow webhook acknowledgement, retry storms |
| Simulation data presented as real Razorpay merchant data | Misleading claim |
| Evaluation metrics computed after seeing agent results and selecting favourable metric | Scientific dishonesty |
| New microservice added because "it might need to scale independently" | Premature microservices |
| Kafka introduced "for reliability" before outbox/inbox is proven insufficient | Technology before problem |
| Agent prompt hardcoded as a string constant in application code | Unversionable agent behaviour |
| Two concurrent recovery actions executing on the same case | Serialisation failure, double execution risk |
| Idempotency key generated from mutable data | Idempotency key collision risk |
| Raw Razorpay webhook payload amount used as authoritative financial amount | Untrusted external input as financial authority |
| `except Exception: pass` in financial action handlers | Silent failure in financial operations |

---

## 18. Questions Every Future Implementation Must Answer

Before writing a single line of implementation code for any component, the following questions must be answerable. If any cannot be answered, the component is not ready to implement.

### Identity and Purpose

1. **Why does this component exist?**  
   What problem does it solve, and why does that problem need to be solved in this system?

2. **What is its single responsibility?**  
   If the answer requires the word "and", reconsider whether this is one component or two.

3. **Which domain does this component belong to?**  
   Financial core, simulation, agent, evaluation, integration adapter, infrastructure?

### AI Justification

4. **Does this component involve AI?**  
   If yes: what exactly is the AI doing that deterministic code cannot do?

5. **Why can't deterministic code solve this?**  
   Be specific. "It's complex" is not a sufficient answer.

6. **If the AI returns nonsense, what happens?**  
   The answer must not be "the system does something financially unsafe."

### Data and State

7. **What is the source of truth for this component's data?**  
   PostgreSQL for durable state. If not, justify explicitly.

8. **What state transitions does this component cause?**  
   Are they logged? Are they reversible? What happens if they fail mid-way?

9. **Is monetary data involved?**  
   If yes: is it stored and calculated as integer minor units? Is it validated deterministically?

### Safety and Reliability

10. **What happens when this component fails?**  
    Is failure safe? Does the system degrade gracefully? Is the failure detectable?

11. **Is this operation idempotent?**  
    If called twice with the same inputs, does it produce the same observable outcome?

12. **What is the financial blast radius of a bug in this component?**  
    What is the worst credible outcome of a defect here?

### Testing

13. **How is the behaviour of this component verified?**  
    Name the specific test types and what they cover.

14. **Can this component be tested without calling external APIs, the LLM, or the database?**  
    If not: why not, and how is integration tested safely?

15. **What are the boundary conditions and edge cases?**  
    Are there tests for: at-limit, just-below, just-above, zero, negative, missing inputs?

### Security and Auditability

16. **Does this component handle credentials or secrets?**  
    If yes: are they loaded from environment variables and never logged?

17. **Is financial safety enforced?**  
    Which deterministic validation does this component's output pass through before execution?

18. **How is the decision or action audited?**  
    What is written to the audit log, and what fields does it include?

19. **What is the correlation ID / decision ID strategy for this component?**  
    How can a single event be traced end-to-end through logs?

### Architectural Fit

20. **Does this component respect the deterministic control layer? (P-03)**  
    Confirm: AI decision -> Policy validation -> Execution. Never AI -> Direct action.

21. **Does this component violate any of the 17 anti-patterns listed in Section 17?**  
    Review the list explicitly before signing off.

22. **Which block does this component belong to?**  
    Is there any dependency on a future block being implemented? If yes, stop and resolve.

---

*End of Financial Agent Lab Project Constitution v1.0*

*This document is the engineering contract. It supersedes verbal agreements, ad-hoc decisions, and convenience shortcuts. Amendments must be recorded as versioned updates to this document with a dated changelog entry.*

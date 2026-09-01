# Production Operations Manual — Financial Agent Lab

**Document Version:** 1.0.0 (Block 8 Production Hardening)  
**System Classification:** Autonomous Recovery Decision & Control Plane (Test Mode Action Execution)  

---

## 1. System Overview & Architectural Boundaries

The **Financial Agent Lab** is a high-assurance financial decision and recovery orchestration platform. It models payment failure recovery, evaluates LLM decision intelligence under strict economic constraints, and safely dispatches recovery interventions via an ACID-compliant PostgreSQL transactional outbox.

### Non-Negotiable Architectural Invariants:
1. **AI Authority Boundary:** The AI (e.g., Gemini 2.5 Flash) is strictly an advisory proposal generator. It has zero mutation privileges over database records, state machines, or payment status.
2. **Deterministic Policy Gate:** All AI proposals are validated deterministically against merchant policies (cooldowns, maximum discounts, intervention caps) prior to approval.
3. **Deterministic Economic Valuation:** The `EconomicEngine` calculates expected net incremental revenue strictly in integer minor units (paise). The LLM never computes financial value.
4. **Authoritative Reconciliation Boundary:** Action execution $\neq$ payment capture. Only verified Razorpay webhook events (`payment.captured`) transition payments to `CAPTURED`.
5. **Execution Mode Disclaimer:** **ALL ACTION EXECUTORS REMAIN IN TEST-MODE.** The system simulates action outcomes with deterministic execution references (`TEST_WAIT_*`, `TEST_RETRY_*`, `TEST_PLINK_*`, `TEST_NOTIF_*`, `TEST_TICKET_*`). Real money movement or live gateway charge operations are NOT enabled.

---

## 2. Environment Configuration & Secrets Management

Configuration is loaded from environment variables using `pydantic-settings` (`apps/api/settings.py`).

### Key Configuration Variables:

| Variable | Type | Default | Description |
|---|---|---|---|
| `APP_ENV` | `str` | `development` | `development`, `test`, or `production`. In `production`, strict secret checks are enforced. |
| `APP_DEBUG` | `bool` | `false` | Enable SQL query echo and debugging routes (disabled in production). |
| `LOG_LEVEL` | `str` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `API_HOST` | `str` | `0.0.0.0` | API bind address. |
| `API_PORT` | `int` | `8000` | API bind port. |
| `ADMIN_API_KEY` | `str` | `None` | Secret key for administrative/simulation endpoints (`X-API-Key` header). |
| `DATABASE_URL` | `str` | *Auto-built* | PostgreSQL connection string. |
| `DB_HOST` | `str` | `localhost` | PostgreSQL host. |
| `DB_PORT` | `int` | `5432` | PostgreSQL port. |
| `DB_NAME` | `str` | `financial_agent_lab` | Database name. |
| `DB_USER` | `str` | `fal_user` | Database user. |
| `DB_PASSWORD` | `str` | `""` | Database password (**Required in production**). |
| `RAZORPAY_WEBHOOK_SECRET` | `str` | `test_webhook_secret_local` | HMAC secret (**Required non-default in production**). |
| `AI_PROVIDER` | `str` | `mock` | `mock`, `gemini`, `openai`, `ollama`. |
| `AI_API_KEY` | `str` | `None` | API key for live LLM providers (MockLLM used during tests). |
| `AI_MODEL` | `str` | `gemini-2.5-flash` | LLM model name. |

---

## 3. Deployment & Startup Procedures

### 3.1 Database Migration
Apply all schema revisions up to `head` before starting service processes:
```bash
# Verify pending migrations
alembic current

# Apply migrations
alembic upgrade head
```

### 3.2 Starting the FastAPI Application
Run the API server using Uvicorn or Gunicorn with Uvicorn workers:
```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 3.3 Starting the Transactional Outbox Worker
Run the dedicated outbox daemon process in background / systemd:
```bash
python -m infrastructure.workers.outbox_worker
```

---

## 4. Health, Readiness & Observability Endpoints

### 4.1 Liveness Probe (`GET /health`)
- **Purpose:** Verifies that the HTTP server process is running and accepting sockets.
- **Response (200 OK):**
  ```json
  {
    "status": "healthy",
    "service": "financial-agent-lab",
    "environment": "production"
  }
  ```

### 4.2 Readiness Probe (`GET /ready`)
- **Purpose:** Verifies PostgreSQL database connectivity and configuration readiness before routing traffic.
- **Response (200 OK):**
  ```json
  {
    "status": "ready",
    "database": "connected",
    "environment": "production",
    "ai_provider": "gemini"
  }
  ```
- **Failure (503 Service Unavailable):** Returned if the database connection fails (without leaking internal passwords or stack traces).

### 4.3 Observability & Decision Telemetry (`GET /observability/summary`)
- **Purpose:** Read-only endpoint serving aggregate operational health, outbox queue metrics, and economic evaluations.
- **Properties:** Strictly read-only; cannot mutate database state or trigger money movements.

---

## 5. Webhook Ingestion & Replay Resilience

1. **HMAC Signature Verification:** Incoming webhooks require constant-time HMAC-SHA256 signature verification over raw request body bytes before JSON deserialization.
2. **Deduplication:** Events are uniquely keyed on `razorpay_event_id`. Duplicate webhook deliveries return `200 OK` (`{"status": "duplicate_ignored"}`) without executing duplicate side effects.
3. **Out-of-Order Handling:** Reconciles event timestamps against existing payment state. Succeeded payments cannot be regressed to failed.

---

## 6. Transactional Outbox & Retry Semantics

1. **Atomic Persistence:** `RecoveryActionORM` (status `APPROVED`) and `RecoveryOutboxEventORM` (status `PENDING`) are written in the exact same PostgreSQL transaction.
2. **Row Locking:** The outbox worker queries pending events using `SELECT ... FOR UPDATE SKIP LOCKED` for lock contention avoidance across distributed workers.
3. **Bounded Exponential Backoff:**
   $$\text{Backoff Seconds} = 2^{\text{retry\_count}} \times 10$$
   - Retryable errors reschedule `next_attempt_at`.
   - On exceeding `max_retries` (default 3) or non-retryable errors, actions transition to terminal `FAILED`.
4. **Stuck Event Reclamation:** Outbox events remaining in `PROCESSING` status for $> 15$ minutes are reclaimed and re-dispatched.

---

## 7. Structured Logging & Correlation Context

- **Correlation ID:** Every request is tagged with an `X-Correlation-ID` header (generated or propagated).
- **Log Format:** Structured JSON or formatted output containing `timestamp`, `level`, `logger`, `correlation_id`, and contextual metadata (`recovery_case_id`, `action_id`).
- **Data Protection:** Automatic regex-based redaction of API keys, passwords, bearer tokens, and payment identifiers.

---

## 8. Graceful Shutdown

- On receiving `SIGTERM` / `SIGINT`:
  1. The API server stops accepting new HTTP connections.
  2. In-flight requests are allowed to complete.
  3. Outbox worker loop exits cleanly and closes active database sessions.
  4. SQLAlchemy `async_engine.dispose()` closes all PostgreSQL pool connections.

---

## 9. Requirements for Real Financial Action Execution

Before transitioning from test-mode action simulation to real financial execution in a future phase, the following prerequisites must be implemented:
1. Replace test-mode action executors with real payment gateway SDKs (Razorpay Payment Links API, Customer Notification Gateway).
2. Establish formal merchant webhook reconciliation signing keys and secret rotation policies.
3. Implement dual-control / human-in-the-loop review queues for actions exceeding merchant risk thresholds.
4. Establish legal and regulatory compliance controls (PCI-DSS, RBI tokenization guidelines).

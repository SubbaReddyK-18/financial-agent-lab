# Observability & Evaluation Guide

## 1. Overview & Architectural Principles

The Observability and Evaluation layer in **Financial Agent Lab** provides deterministic telemetry, audit traceability, and comparative economic benchmarking for autonomous recovery decisions.

### Core Principles
1. **Measurement, Not Authority**: The observability layer strictly measures and evaluates system behavior; it never alters financial transactions, transitions payment states, or overrides merchant policies.
2. **Authoritative Monetary Truth**: All monetary values are computed and aggregated exclusively in **integer minor units (paise)** by the deterministic `EconomicEngine`. No floating-point approximations are ever used for financial balances.
3. **Partitioning of Live vs. Offline Synthetic Data**:
   - **Live Production Metrics**: Reconstructed strictly from observable production records (`AIDecisionRecordORM`, `RecoveryActionORM`, `RecoveryCaseORM`, `PaymentORM`).
   - **Simulation Evaluations**: Clearly labeled `source_type = "SYNTHETIC_SIMULATION"`. Hidden simulation ground truth is strictly quarantined in offline benchmark runners and never enters production contexts.

---

## 2. Metric Definitions & Mathematical Formulas

### A. Operational Health Metrics

| Metric | Formula / Definition | Purpose |
|---|---|---|
| **Total Decisions ($N$)** | Count of all decision records. | Total recovery evaluation volume. |
| **Fallback Rate ($R_{\text{fb}}$)** | $\frac{N_{\text{fallback}}}{N}$ | Fraction of decisions handled by deterministic baseline due to AI error, timeout, 429, or policy rejection. |
| **Policy Rejection Rate ($R_{\text{rej}}$)** | $\frac{N_{\text{policy\_rejections}}}{N}$ | Proportion of raw AI proposals that violated merchant policy constraints (e.g., max interventions, discount caps, cooldown). |
| **P50 / P95 / P99 Latency** | Linear interpolated percentiles of inference and orchestration latency. | Operational SLA and tail-latency monitoring. |

### B. Economic Metrics (Paise Arithmetic)

| Metric | Formula / Definition | Unit |
|---|---|:---:|
| **Expected Gross Revenue** | $P(\text{recovery}) \times \text{Amount}$ | Integer Paise |
| **Expected Natural Recovery** | $P(\text{natural}) \times \text{Amount}$ | Integer Paise |
| **Expected Incremental Revenue** | $\text{Gross} - \text{Natural} - \text{Discount}$ | Integer Paise |
| **Expected Net Incremental Value** | $\text{Incremental} - \text{Intervention Cost} - \text{LLM Cost}$ | Integer Paise |
| **Realized Captured Revenue** | Total observed captured payments associated with recovery cases (causal incremental attribution is unidentifiable in single-stream live production). | Integer Paise |

### C. Simulation Benchmark Metrics

| Metric | Formula / Definition | Description |
|---|---|---|
| **Economic Value Capture Ratio** | $\frac{\text{Net Revenue}_{\text{AI}}}{\text{Net Revenue}_{\text{Oracle}}}$ | Ratio of theoretical maximum incremental value captured by AI. |
| **Net Economic Lift** | $\text{Net Revenue}_{\text{AI}} - \text{Net Revenue}_{\text{Baseline}}$ | Incremental financial value created by AI over deterministic heuristic rules. |
| **Per-Scenario Regret** | $\max(0, \text{Net}_{\text{Oracle}} - \text{Net}_{\text{AI}})$ | Economic opportunity loss relative to ground truth optimal action. |
| **Near-Optimality Rates** | $\% \text{ scenarios where } \frac{\text{Regret}}{\text{Net}_{\text{Oracle}}} \le \epsilon$ ($\epsilon \in \{1\%, 5\%, 10\%\}$) | Measure of decisions within a tight margin of optimal. |

---

## 3. Probability Calibration & Reliability

To evaluate the predictive accuracy of model probability estimates against simulator ground truth, the evaluator measures:

1. **Natural Recovery Probability MAE**:
   $$\text{MAE}_{\text{natural}} = \frac{1}{N} \sum_{i=1}^N \left| P_{\text{pred}}(\text{natural}_i) - P_{\text{true}}(\text{natural}_i) \right|$$
2. **Action Recovery Probability MAE**:
   $$\text{MAE}_{\text{action}} = \frac{1}{N} \sum_{i=1}^N \left| P_{\text{pred}}(\text{action}_i) - P_{\text{true}}(\text{action}_i) \right|$$
3. **Brier Score** (Mean Squared Error against binary realized outcome):
   $$\text{BS} = \frac{1}{N} \sum_{i=1}^N \left( P_{\text{pred}}(\text{action}_i) - y_i \right)^2 \quad (y_i \in \{0, 1\})$$
4. **Calibration Buckets**: 5 uniform probability bins ($[0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), [0.8, 1.0]$) mapping mean predicted confidence to observed empirical recovery rates.

---

## 4. Model Version Comparison Methodology

The `ModelVersionComparator` enables champion-challenger testing:
- **Identical Scenarios**: Multiple candidate models and prompt versions are evaluated against the exact same synthetic scenario batch.
- **Evaluation Criteria**: Challenger is considered superior if:
  1. It achieves a higher Economic Value Capture Ratio, OR
  2. It generates higher Net Economic Value with equal or lower Mean Regret.

---

## 5. Synthetic Simulation Disclaimer

> [!IMPORTANT]
> **DISCLAIMER**: The Simulation Oracle and synthetic evaluations represent mathematically modeled counterfactual environments. They are utilized strictly for offline regression testing and calibration benchmarking. Performance ratios must not be construed as guaranteed real-world customer recovery outcomes.

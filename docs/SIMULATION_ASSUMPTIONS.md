# Simulation Assumptions & Methodology

> [!NOTE]
> **SIMULATION HONESTY DECLARATION**: All probability values, customer responsiveness distributions, and intervention costs in this document and throughout Block 3 are **SYNTHETIC LABORATORY ASSUMPTIONS** designed to evaluate economic decision algorithms under controlled, reproducible conditions. They do **NOT** represent Razorpay's proprietary commercial data, live merchant conversion metrics, or empirical banking statistics.

---

## 1. Primary Economic Objective

The Economic Engine evaluates candidate recovery actions based on **Expected Net Incremental Revenue**:

$$\text{Expected Net Incremental Revenue} = \text{Expected Gross Revenue With Action} - \text{Expected Natural Recovery Revenue} - \text{Intervention Cost}$$

Where:
- **Expected Gross Revenue**: $\text{Amount} \times P(\text{Recovery} \mid \text{Action}) \times (1 - \text{Discount Rate})$
- **Expected Natural Revenue**: $\text{Amount} \times P(\text{Natural Recovery} \mid \text{No Action})$
- **Intervention Cost**: Direct operational, communication, or human escalation cost in minor units (paise).

All authoritative monetary amounts are strictly maintained as **integer minor units (paise)** to avoid IEEE 754 floating-point inaccuracies.

---

## 2. Failure Category Taxonomy & Probability Distributions

Scenarios are categorized into three distinct failure regimes:

| Failure Category | Examples | Scenario Distribution | Natural Recovery $P(\text{Natural})$ | Retry Success $P(\text{Retry})$ | Link Success $P(\text{Link})$ | Notification $P(\text{Notify})$ | Escalation $P(\text{Escalate})$ |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Technical Transient** | `GATEWAY_TIMEOUT`, `NETWORK_ERROR`, `ISSUER_DOWN`, `PROCESSING_ERROR` | 45% | $0.25 - 0.45$ | $0.60 - 0.85$ | $0.40 - 0.60$ | $0.35 - 0.50$ | $0.70 - 0.90$ |
| **Customer Actionable** | `MPIN_EXPIRED`, `OTP_TIMEOUT`, `AUTHENTICATION_FAILED`, `USER_DROPPED` | 35% | $0.10 - 0.25$ | $0.20 - 0.40$ | $0.55 - 0.80$ | $0.50 - 0.70$ | $0.65 - 0.85$ |
| **Terminal / Balance** | `INSUFFICIENT_FUNDS`, `ACCOUNT_BLOCKED`, `INVALID_ACCOUNT`, `CARD_EXPIRED` | 20% | $0.02 - 0.08$ | $0.05 - 0.15$ | $0.15 - 0.30$ | $0.10 - 0.25$ | $0.25 - 0.45$ |

---

## 3. Operational Cost Assumptions

Operational costs represent the marginal cost to execute an intervention:

| Recovery Action | Simulated Cost (Minor Units) | Simulated Cost (INR) | Operational Rationale |
|---|:---:|:---:|---|
| **WAIT** | `0` | ₹0.00 | Passive observation, zero operational expense. |
| **NOTIFY** | `15` | ₹0.15 | Automated SMS / WhatsApp business message delivery cost. |
| **RETRY** | `20` | ₹0.20 | Payment gateway API invocation & switch routing cost. |
| **PAYMENT_LINK** | `50` | ₹0.50 | Dynamic payment link generation, short-URL hosting, multi-channel dispatch. |
| **ESCALATE** | `500` | ₹5.00 | Human operations ticket creation, customer support rep routing. |

---

## 4. Scenario Generation Distributions

1. **Amount Tiers**:
   - Micro (₹50 – ₹499): 30% of scenarios.
   - Standard (₹500 – ₹2,500): 50% of scenarios.
   - High-Value (₹5,000 – ₹50,000): 20% of scenarios.
2. **Payment Methods**:
   - UPI: 60%
   - Card: 25%
   - Netbanking: 10%
   - Wallet: 5%
3. **Customer Segments**:
   - Returning / Standard: 50%
   - New: 20%
   - VIP: 15% (eligible for discount offers up to policy maximum)
   - At-Risk: 15%

---

## 5. Counterfactual Diagnostic Classifications

- **Unnecessary Intervention**: An intervention was executed ($\text{Action} \neq \text{WAIT}$), but the customer would have naturally completed the payment without intervention ($W_A = \text{True}$ and $W_B = \text{True}$). The intervention cost was spent unnecessarily.
- **Missed Opportunity**: The system chose $\text{WAIT}$, natural recovery did not occur ($W_A = \text{False}$), but a permitted alternative action had positive expected net incremental revenue and would have successfully recovered the payment.

---

## 6. What the Simulation Does NOT Prove

1. **Not Causal Ground Truth for Real Merchants**: Synthetic Bernoulli trials are mathematical models of decision dynamics under uncertainty, not causal proofs of real human customer psychology.
2. **Static Independent Trials**: Does not model multi-day customer fatigue from continuous spam across multiple merchant checkouts.
3. **Deterministic Bounds**: Real-world payment networks have unobserved latent variables (e.g. telecom outages, holiday shopping surges) not captured by uniform parameter intervals.

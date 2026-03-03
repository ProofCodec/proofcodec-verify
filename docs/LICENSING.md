# ProofCodec Licensing Strategy

## Overview

ProofCodec uses a split-license model designed to maximize adoption, protect IP during patent prosecution, and eliminate enterprise procurement friction. The structure is deliberately asymmetric: everything a customer needs to *verify* and *decode* is permissively licensed; everything needed to *encode* is proprietary.

## License Matrix

| Component | License | Rationale |
|---|---|---|
| Decoder library (Python) | MIT | Zero-friction adoption. No legal review needed. Customers embed freely. |
| Standalone verifier | MIT | Credibility move -- anyone can independently verify compression claims. |
| Proof bundle format spec | CC-BY-4.0 | Open standard. Encourages third-party tooling and ecosystem growth. |
| Encoder pipeline | Proprietary (closed source) | Core IP protection until patent granted. |
| Feature engineering | Proprietary / per-client | Custom consulting value. Domain-specific expertise is the moat. |

## Why This Structure (Not BSL)

We evaluated Business Source License (BSL/BUSL), SSPL, and Elastic License. All were rejected for specific reasons:

**Patent prosecution safety.** The encoder pipeline contains patent-pending methods for decision-tree-based policy compression with MDL residual encoding. Publishing source code -- even under a restrictive license -- creates prior art risk. Keeping the encoder closed-source avoids this entirely. No source publication means no prior art concern.

**No fork risk.** BSL and similar licenses allow source inspection, which enables clean-room reimplementation. With a proprietary encoder, there is nothing to fork. The decoder alone is useless for compression -- it only reads proof bundles the encoder produces.

**Enterprise legal teams have zero concerns.** MIT is the most permissive, most widely understood license in enterprise software. Legal teams approve MIT dependencies without escalation. BSL, SSPL, and similar licenses trigger procurement reviews, legal holds, and sometimes outright bans (e.g., AWS policy on SSPL). MIT decoder = normal commercial software, no friction.

**Open verifier provides full credibility.** The MIT-licensed standalone verifier allows any third party -- auditors, regulators, customers, competitors -- to independently verify that a proof bundle is valid. This is the single most important trust-building asset ProofCodec has. If we claimed 10-39,000x compression and the verifier were proprietary, no one would believe us.

**Future flexibility.** If and when the patent grants, we can consider making the encoder source-available (e.g., BSL with a 3-year conversion to Apache-2.0). The current structure does not foreclose this option. It simply defers the decision until IP protection is secured through the patent system rather than through license restrictions.

## Customer Assurance

The MIT verifier + decoder ensures that if ProofCodec disappears, your proof bundles still work. Specifically:

- **Decoder continuity.** The MIT-licensed decoder can be forked, maintained, and distributed by anyone, indefinitely. There is no license key, no phone-home, no time bomb.
- **Verification continuity.** The MIT-licensed verifier can independently confirm that any existing proof bundle is valid. No dependency on ProofCodec infrastructure.
- **Format durability.** The CC-BY-4.0 proof bundle format spec is a public document. Any competent engineer can build a compatible decoder from the spec alone.

In practice, this means a customer's compliance artifacts (timestamped proof bundles) remain independently verifiable even in a worst-case scenario where ProofCodec ceases operations.

## Distribution Summary

```
Open (MIT / CC-BY-4.0)          Proprietary
-------------------------------  -------------------------------
proofcodec-decoder (PyPI)        Encoder pipeline (API / on-prem)
proofcodec-verify (standalone)   Feature engineering libraries
Proof bundle format spec         Domain-specific consulting
API client SDKs                  Hosted encoding service
```

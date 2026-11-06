# AI Platform Forge — Product Requirements

This document records the broader product direction. The first implementation is the single-user local document workspace described in [Architecture.md](Architecture.md). Its observed verification results are in [Results.md](Results.md); the full eleven-area platform remains a roadmap.

## Problem and audience
Engineers learning enterprise AI need evidence that they can integrate, evaluate, govern, and operate a complete system. Isolated tutorials and provider demos leave gaps between model calls and reliable workflows. The assumed current workaround is separate experiments with inconsistent evaluation and operational evidence; validate this assumption with intended users before implementation.

The primary user is an AI/platform engineer building demonstrable skills. Secondary users are reviewers assessing reproducible engineering evidence and operators diagnosing failures. The product is a local-first reference lab with optional approved cloud and GPU experiments.

## Outcome and scope
Deliver a document-to-answer workflow: ingest synthetic documents, extract and index content, retrieve authorized evidence, execute a bounded agent, stream a cited answer, and inspect quality, safety, latency, and cost. Add ML lifecycle, GPU scheduling, and simulated physical AI as staged extensions.

No production operations, real robot actuation, unrestricted autonomous agents, customer data, or mandatory paid services are in scope. This documentation does not authorize dependency installation, cloud spending, external data transfer, or deployment.

## Requirements and acceptance
| ID | Requirement | Observable acceptance |
|---|---|---|
| F01 | Provider abstraction for AWS Bedrock, Azure Foundry, and Gemini Enterprise Agent Platform | Each planned adapter has a capability record and contract suite; at least one approved sandbox integration is exercised before claiming live integration. |
| F02 | Governed agent runtime | A run resumes from a durable checkpoint without duplicating a completed side effect; invalid outputs and disallowed models fail closed. |
| F03 | Document AI and RAG | Text and scanned fixtures retain page-level provenance through OCR, segmentation, retrieval, ranking, and cited answers. |
| F04 | Search experiments | Compare keyword, vector, and hybrid retrieval on the same held-out queries; report ranking and embedding-service effects separately. |
| F05 | Optimization experiments | Compare streaming and non-streaming latency; record prompt/model versions and an evidence-based fine-tuning decision. |
| F06 | Evaluation and safety | Regression, failure analysis, injection, content safety, fairness, and calibrated abstention checks produce reviewable results. |
| F07 | ML lifecycle | A scikit-learn baseline has tracked experiments, versioned artifacts, drift monitoring, and a bounded retraining workflow with human promotion. |
| F08 | GPU infrastructure | Compare a bin-packing scheduler with a simple baseline under quotas; distinguish simulated allocation from NVIDIA/CUDA hardware execution. |
| F09 | Observability | Correlate ingestion, retrieval, model calls, tools, and scheduler activity through OpenTelemetry; verify Application Insights export in an approved sandbox. |
| F10 | Physical AI lab | A ROS/ROS2 simulation demonstrates edge disconnection, stale-data handling, and safe stop without enabling physical actuation. |
| F11 | Development-tool assessment | Compare GitHub Copilot Enterprise, Claude Code, Managed Agents, OpenAI Codex, and Cursor using a fixed task rubric and permitted data. |

## User journey
1. Select a versioned lab profile and inspect its data, provider, hardware, and budget requirements.
2. Load synthetic fixtures; inspect extraction failures, OCR confidence, and indexing status.
3. Ask a question; observe retrieval, streaming status, sources, and uncertainty.
4. Inspect the run timeline, policy decisions, errors, and measured outcomes.
5. Compare a candidate configuration with a frozen baseline; export the evidence bundle for review.

Empty states explain the next action. Permission failures explain the missing scope. Timeouts and partial streams expose incomplete status; unsupported evidence leads to abstention. Cancellation stops downstream work within a configured deadline.

## Success and release conditions
Proposed targets, not measured results: first offline successful run within 30 minutes of documented setup; zero cross-tenant retrieval in the mandatory isolation suite; every accepted answer citation resolves to an authorized source version; all critical safety assertions pass. Performance and quality thresholds are defined in [Evaluation.md](Evaluation.md).

The agreed first release covers local document ingestion, retrieval, bounded generation, and a subset of F02–F06 using real Ollama models. Cloud adapters and broader safety studies are later work. Remaining providers, developer-tool comparisons, ML, GPU, and physical AI are later milestones. MVP completion does not imply closure of all skill gaps.

## Decisions still needed
Assign product, security, evaluation, and operations owners; validate the audience; approve provider accounts and data regions; resolve the intended product behind “Managed Agents”; verify current provider/product names and API capabilities against primary documentation. The original directory contained only planning documents. The current local implementation and its limits are documented in the architecture and results report.

## Document map
- [Skills.md](Skills.md): all 11 gaps, practice tasks, and evidence of competence.
- [Architecture.md](Architecture.md): proposed components, boundaries, contracts, and decisions.
- [Roadmap.md](Roadmap.md): delivery sequence, exit criteria, risks, and next tasks.
- [Evaluation.md](Evaluation.md): experiments, acceptance gates, and operational validation.

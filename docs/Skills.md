# Skills and Evidence Matrix

This matrix tracks the broader learning backlog; the local application implements only part of it. These are engineering competencies, not executable agent instructions or a claim of proficiency. Requirements are defined in [PRD.md](PRD.md); gates are defined in [Evaluation.md](Evaluation.md).

## Coverage of the supplied gaps
| Gap | Competencies to develop | Practical work and required evidence | Stage |
|---|---|---|---|
| 1. AI platforms | AWS Bedrock; Azure Foundry; Gemini Enterprise Agent Platform | Build adapter contract tests, document identity/region/retention constraints, run the same approved task per platform, and report unsupported features explicitly. | M2/M3 |
| 2. AI development tools | GitHub Copilot Enterprise; Claude Code; Managed Agents; OpenAI Codex; Cursor | Use isolated copies of a fixed repository task; measure correctness, review effort, time, data policy, and reproducibility. Resolve “Managed Agents” before comparison. | M3 |
| 3. Agent engineering | Agentic memory; context management; workflow state; structured outputs; model allowlisting; retries; fallback strategies | Implement scoped expiring memory, token budgets, checkpoint/resume, schema validation, allowlist checks, bounded retries, cancellation, and policy-preserving fallback; retain failure traces. | M1/M2 |
| 4. RAG and knowledge engineering | Document segmentation/chunking; embeddings; embedding-service evaluation; keyword search; hybrid search; result ranking; retrieval evaluation; knowledge graphs; taxonomies; provenance; citations | Compare chunking and embedding configurations on held-out queries; test keyword/vector/hybrid plus reranking; build a small taxonomy and graph; retain lineage and citation checks. | M1–M3 |
| 5. Document AI | Document processing; document analysis; optical character recognition (OCR) | Process digital, scanned, rotated, and table-heavy fixtures; report extraction accuracy and OCR errors with page/bounding-box provenance where available. | M1 |
| 6. LLM optimization | Response streaming; streaming inference; latency optimization; fine-tuning trade-offs; prompt/model versioning | Measure first-token and complete-response latency under fixed load; test interrupted streams; compare prompt/RAG improvements before proposing fine-tuning. | M2/M3 |
| 7. AI evaluation and safety | Regression testing; failure-mode detection; structured error analysis; confidence thresholds; prompt-injection defences; content safety; fairness; AI risk/bias mitigation | Maintain golden/adversarial sets, error taxonomy, calibrated abstention, subgroup reports, and deterministic policy assertions; record residual risks. | M1 onward |
| 8. ML/MLOps | scikit-learn; experiment tracking; model versioning; drift detection; automated retraining | Train a small document classifier with leakage-resistant splits; register artifacts and lineage; simulate drift, trigger sandbox retraining, and block promotion until review. | M4 |
| 9. GPU/AI infrastructure | NVIDIA environments; CUDA; GPU telemetry; GPU workload orchestration/scheduling/scaling; LLM gateways; model serving; bin-packing; resource allocation | Create a quota-aware scheduling simulation, then an optional approved hardware lab; measure queue time, packing efficiency, memory pressure, scaling behavior, and serving latency. | M4 |
| 10. Infrastructure observability | OpenTelemetry; Application Insights | Trace the complete workflow with correlated errors and resource attributes; test redaction and collector failure; verify exporter delivery separately from local tracing. | M1/M3 |
| 11. Physical AI | Robotics; ROS/ROS2; distributed edge applications; training/hybrid workload optimization | Run simulation-only edge workloads with heartbeat expiry and safe stop; compare edge/cloud placement and training/inference contention under disconnection. | M5 |

## Evidence rubric
- Level 0 — planned: requirements and experiment protocol exist.
- Level 1 — implemented: code and reproducible fixtures exist.
- Level 2 — tested offline: named checks pass with mocks or simulation; limits recorded.
- Level 3 — integrated: approved real service or hardware boundary tested with retained evidence.
- Level 4 — evaluated: held-out task results, failure analysis, and independent human review recorded.

No personal proficiency level is assigned. Local implementation and test evidence is recorded in [Results.md](Results.md). Track each skill separately: simulation cannot establish hardware competence, and one provider cannot establish another provider's integration.

## Evidence record
For each exercise record: skill and requirement IDs; author/reviewer; revision; environment; exact commands; dependency, provider, model and dataset versions; baseline; sample size; results; failed cases; cost; limitations; artifact locations; next decision. Do not retain secrets or unrestricted prompt/document content.

## Practice order
Start with document ingestion, retrieval, typed agent contracts, and observability. Add live platforms and optimization once offline evidence is stable. Follow with developer-tool comparisons, ML/GPU experiments, and simulated edge/robotics. Use [Roadmap.md](Roadmap.md) for milestone exits.
